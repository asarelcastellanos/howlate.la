"""Rebuild each rail vehicle's real runs from positions, and test the reported trip id.

Run on the backfill VM as

    python pipeline/scripts/rail_runs.py --service-date YYYYMMDD --cache DIR --out DIR

or on local files with no bucket access

    python pipeline/scripts/rail_runs.py --service-date YYYYMMDD --out DIR \
        --raw-dir RAW --gtfs-dir GTFS_RAIL

where GTFS_RAIL holds the unpacked rail timetable. See "Finding why rail trip
ids disagree" in pipeline/README.md.

A run is one vehicle going one way along one route. It is found from latitude and
longitude alone. Each position is snapped to the nearest station of the route
within RADIUS_M, and a vehicle that reverses along the station order, or is
missing for GAP_S, starts a new run. Where two routes share track, the route
that explains the most stations wins. The reported trip_id is never used to cut
runs.

Each run is then fitted to the running trips of its route and direction. The
fit of a trip is the median, over the stations both pass, of the seconds between
the vehicle's time and the scheduled time. The trip with the lowest median is the
ground-truth trip of the run. A run is confident when that median is at most
CONFIDENT_FIT_S and the next trip is at least CONFIDENT_MARGIN_S worse, because
a vehicle that is late by half a headway fits two trips equally and the times
alone cannot choose.

The ids the vehicle reported while the run lasted are then classed against the
ground-truth trip.

    match          the id is the ground-truth trip
    stale          the id is the ground-truth trip of the vehicle's previous run
    same_line      another trip on the same route and direction
    other_route    a running trip on another route or direction
    not_in_force   a listed trip whose service is not running that day, split
                   into later_start and other_service in `subclass`
    unknown        not in any timetable copy read
    none           no id on any record of the run

Writes OUT/rail_runs_DAY.json, one summary per route, and OUT/rail_runs_DAY.csv,
one row per run.
"""

import argparse
import bisect
import csv
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from howlate_pipeline import RAIL_AGENCY, arrivals, gtfs  # noqa: E402
from howlate_pipeline.__main__ import Bucket  # noqa: E402

RADIUS_M = 300
MAP_M = 300
MERGE_S = 600
GAP_S = 2400
MIN_STATIONS = 3
MIN_COMMON = 3
CONFIDENT_FIT_S = 120
CONFIDENT_MARGIN_S = 120
LAYOVER_S = 3600
DAY_START_S = 2 * 3600
DAY_END_S = 27 * 3600

CLASSES = ["match", "stale", "same_line", "other_route", "not_in_force", "unknown", "none"]

EXTRACT = """
SELECT
  json_extract_string(j, '$.payload.vehicle.vehicle.id')       AS vehicle_id,
  CAST(json_extract_string(j, '$.payload.vehicle.timestamp') AS BIGINT) AS ts,
  CAST(json_extract_string(j, '$.payload.vehicle.position.latitude') AS DOUBLE)  AS lat,
  CAST(json_extract_string(j, '$.payload.vehicle.position.longitude') AS DOUBLE) AS lon,
  json_extract_string(j, '$.payload.vehicle.trip.tripId')      AS trip_id,
  json_extract_string(j, '$.payload.vehicle.trip.startDate')   AS start_date,
  json_extract_string(j, '$.payload.vehicle.trip.startTime')   AS start_time,
  json_extract_string(j, '$.payload.vehicle.trip.routeId')     AS route_id,
  json_extract_string(j, '$.payload.vehicle.trip.directionId') AS direction_id
FROM read_json_objects(?) t(j)
WHERE json_extract_string(j, '$.agency') = ?
"""


@dataclass
class Trip:
    trip_id: str
    route: str
    direction: int | None
    active: bool
    later: bool
    stops: list
    first_dep: int


@dataclass
class Stretch:
    k: int
    first: int
    best: int
    last: int
    dist: float


def clock(text: str | None) -> int | None:
    """A GTFS clock such as 25:30:00 as seconds from the service day's base."""
    try:
        hours, minutes, seconds = (int(part) for part in text.strip().split(":"))
    except (AttributeError, ValueError):
        return None
    return hours * 3600 + minutes * 60 + seconds


def read_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def load_timetable(directories: list[Path], service_date: str) -> tuple[dict, dict]:
    """Every trip any copy lists, running or not, and every stop's coordinates.

    The first copy wins for a trip id. A trip id never differs between copies
    (#166), so a later copy only adds the trips the first one lacks.
    """
    trips: dict[str, Trip] = {}
    coords: dict[str, tuple[float, float]] = {}
    for directory in directories:
        active = gtfs.active_services(directory, service_date)
        later = gtfs.later_start_services(directory, service_date)
        for row in read_rows(directory / "stops.txt"):
            try:
                coords.setdefault(row["stop_id"], (float(row["stop_lat"]), float(row["stop_lon"])))
            except ValueError:
                continue
        meta = {r["trip_id"]: r for r in read_rows(directory / "trips.txt")}
        stops = defaultdict(list)
        for row in read_rows(directory / "stop_times.txt"):
            if row["trip_id"] in meta and row["trip_id"] not in trips:
                arr = clock(row["arrival_time"])
                dep = clock(row["departure_time"])
                arr, dep = arr if arr is not None else dep, dep if dep is not None else arr
                if arr is not None:
                    stops[row["trip_id"]].append(
                        (int(row["stop_sequence"]), row["stop_id"], arr, dep)
                    )
        for trip_id, rows in stops.items():
            row = meta[trip_id]
            rows.sort()
            direction = row.get("direction_id", "")
            trips[trip_id] = Trip(
                trip_id,
                row["route_id"],
                int(direction) if direction.isdigit() else None,
                row["service_id"] in active,
                row["service_id"] in later,
                rows,
                rows[0][3],
            )
    return trips, coords


def metres(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dy = (lat2 - lat1) * 110540
    dx = (lon2 - lon1) * 111320 * math.cos(math.radians(lat1))
    return math.hypot(dx, dy)


def nearest(lat: float, lon: float, stations: list) -> tuple[int, float]:
    return min(
        ((k, metres(lat, lon, slat, slon)) for k, (slat, slon) in enumerate(stations)),
        key=lambda pair: pair[1],
    )


def build_routes(trips: dict, coords: dict) -> dict:
    """For each running route, its stations in order and its trips as {station: times}.

    The stations are the stops of the running trip with the most stops. Every
    trip's stops are mapped onto them by coordinates, not by stop_id, because
    the two directions can use different platform ids at one station.
    """
    by_route = defaultdict(list)
    for trip in trips.values():
        if trip.active and trip.direction is not None:
            by_route[trip.route].append(trip)
    routes = {}
    for route, listed in by_route.items():
        ref = max(listed, key=lambda t: len(t.stops))
        stations = [coords[s[1]] for s in ref.stops if s[1] in coords]
        fits = defaultdict(list)
        for trip in listed:
            mapped = {}
            for _, stop_id, arr, dep in trip.stops:
                if stop_id in coords:
                    k, dist = nearest(*coords[stop_id], stations)
                    if dist <= MAP_M:
                        mapped.setdefault(k, (arr, dep))
            fits[trip.direction].append((trip, mapped))
        routes[route] = {"stations": stations, "ref_direction": ref.direction, "fits": fits}
    return routes


def stretches(samples: list, stations: list) -> list[Stretch]:
    """The stations a vehicle was within RADIUS_M of, in order, with when.

    `first` is when it came within range, `last` the final sample there, and
    `best` the sample nearest the station. A vehicle dwelling at a terminal is
    one stretch from arrival to departure.
    """
    found: list[Stretch] = []
    for ts, lat, lon in samples:
        k, dist = nearest(lat, lon, stations)
        if dist > RADIUS_M:
            continue
        if found and found[-1].k == k and ts - found[-1].last <= MERGE_S:
            found[-1].last = ts
            if dist < found[-1].dist:
                found[-1].best, found[-1].dist = ts, dist
        else:
            found.append(Stretch(k, ts, ts, ts, dist))
    return found


def split_runs(found: list[Stretch]) -> list[tuple[int, list[Stretch]]]:
    """Cut the stations into runs. Returns (sign along the station order, stretches).

    A reversal starts a new run at the station where the vehicle turned, so a
    terminal is the end of one run and the origin of the next.
    """
    runs, current, sign = [], [], 0
    for stretch in found:
        if current:
            step = stretch.k - current[-1].k
            direction = (step > 0) - (step < 0)
            if stretch.first - current[-1].last > GAP_S or direction == 0:
                runs.append((sign, current))
                current = []
            elif sign and direction != sign:
                runs.append((sign, current))
                current = [current[-1]]
            if current:
                sign = direction
        current.append(stretch)
    runs.append((sign, current))
    return [(s, r) for s, r in runs if len(r) >= MIN_STATIONS and s != 0]


def overlaps(a: dict, b: dict) -> bool:
    shared = min(a["end"], b["end"]) - max(a["start"], b["start"])
    return shared > 0.5 * min(a["end"] - a["start"], b["end"] - b["start"])


def vehicle_runs(samples: list, routes: dict) -> list[dict]:
    """The runs of one vehicle, each route's candidates pruned by stations explained."""
    candidates = []
    for route, info in routes.items():
        for sign, run in split_runs(stretches(samples, info["stations"])):
            direction = info["ref_direction"] if sign > 0 else 1 - info["ref_direction"]
            times = {run[0].k: run[0].last, run[-1].k: run[-1].first}
            times.update({s.k: s.best for s in run[1:-1]})
            candidates.append(
                {
                    "route": route,
                    "direction": direction,
                    "start": run[0].last,
                    "end": run[-1].first,
                    "times": times,
                    "origin": run[0].k,
                    "stations": len(run),
                }
            )
    chosen: list[dict] = []
    for run in sorted(candidates, key=lambda r: -r["stations"]):
        if not any(overlaps(run, other) for other in chosen):
            chosen.append(run)
    return sorted(chosen, key=lambda r: r["start"])


def fit_run(run: dict, routes: dict, base: int) -> dict:
    """Fit a run to every running trip on its route and direction."""
    scored = []
    for trip, mapped in routes[run["route"]]["fits"][run["direction"]]:
        signed = []
        for k, ts in run["times"].items():
            if k in mapped:
                arr, dep = mapped[k]
                signed.append(ts - base - (dep if k == run["origin"] else arr))
        if len(signed) >= MIN_COMMON:
            scored.append(
                (
                    statistics.median(abs(x) for x in signed),
                    statistics.median(signed),
                    len(signed),
                    trip,
                )
            )
    scored.sort(key=lambda row: row[0])
    if not scored:
        return {"best": None}
    second = scored[1][0] if len(scored) > 1 else None
    miss, delay, common, trip = scored[0]
    confident = miss <= CONFIDENT_FIT_S and (second is None or second - miss >= CONFIDENT_MARGIN_S)
    return {
        "best": trip,
        "miss": miss,
        "second": second,
        "delay": delay,
        "common": common,
        "confident": confident,
    }


def modal(values: list):
    counts = Counter(v for v in values if v is not None)
    return counts.most_common(1)[0][0] if counts else None


def classify(reported, run: dict, trips: dict, prev_best) -> tuple[str, str]:
    best = run["best"]
    if reported is None:
        return "none", ""
    if reported == best.trip_id:
        return "match", ""
    if prev_best is not None and reported == prev_best.trip_id:
        return "stale", ""
    info = trips.get(reported)
    if info is None:
        return "unknown", ""
    if not info.active:
        return "not_in_force", "later_start" if info.later else "other_service"
    if info.route != run["route"] or info.direction != run["direction"]:
        return "other_route", "route" if info.route != run["route"] else "direction"
    return "same_line", ""


def analyse(con, trips: dict, routes: dict, base: int) -> list[dict]:
    rows = con.execute(
        "SELECT DISTINCT vehicle_id, ts, lat, lon, trip_id, start_time, route_id, direction_id "
        "FROM rail WHERE vehicle_id IS NOT NULL ORDER BY vehicle_id, ts"
    ).fetchall()
    by_vehicle = defaultdict(list)
    for row in rows:
        by_vehicle[row[0]].append(row)

    order = {}
    for key in {(t.route, t.direction) for t in trips.values() if t.active}:
        listed = sorted(
            (t for t in trips.values() if t.active and (t.route, t.direction) == key),
            key=lambda t: (t.first_dep, t.trip_id),
        )
        order.update({t.trip_id: i for i, t in enumerate(listed)})

    out = []
    for vehicle, records in by_vehicle.items():
        samples = [(r[1], r[2], r[3]) for r in records if r[2] is not None and r[3] is not None]
        runs = vehicle_runs(samples, routes)
        for run in runs:
            run.update(fit_run(run, routes, base))
        runs = [r for r in runs if r["best"] is not None]
        stamps = [r[1] for r in records]
        previous_end = None
        for i, run in enumerate(runs):
            lo = bisect.bisect_left(stamps, run["start"])
            hi = bisect.bisect_right(stamps, run["end"])
            inside = records[lo:hi]
            ids = [r[4] for r in inside if r[4] is not None]
            reported = modal(ids)
            prev_best = runs[i - 1]["best"] if i else None
            next_best = runs[i + 1]["best"] if i + 1 < len(runs) else None
            kind, subclass = classify(reported, run, trips, prev_best)
            best = run["best"]
            info = trips.get(reported)
            start_time = clock(modal([r[5] for r in inside]))

            changes = [
                (inside[j][1] - run["start"]) / max(run["end"] - run["start"], 1)
                for j in range(1, len(inside))
                if inside[j][4] is not None
                and inside[j - 1][4] is not None
                and inside[j][4] != inside[j - 1][4]
            ]
            floor = max(previous_end if previous_end is not None else 0, run["start"] - LAYOVER_S)
            before = [r[4] for r in records[bisect.bisect_left(stamps, floor) : lo] if r[4]]

            offset_trips = offset_min = None
            if (
                info is not None
                and info.route == run["route"]
                and info.direction == run["direction"]
            ):
                offset_min = (info.first_dep - best.first_dep) / 60
                if info.active:
                    offset_trips = order[reported] - order[best.trip_id]
            elif info is not None and not info.active and info.route == run["route"]:
                offset_min = (info.first_dep - best.first_dep) / 60

            out.append(
                {
                    "vehicle": vehicle,
                    "route": run["route"],
                    "direction": run["direction"],
                    "start": run["start"],
                    "end": run["end"],
                    "stations": run["stations"],
                    "best_trip": best.trip_id,
                    "best_first_dep_min": round(best.first_dep / 60, 1),
                    "miss_s": round(run["miss"]),
                    "second_miss_s": None if run["second"] is None else round(run["second"]),
                    "common": run["common"],
                    "delay_s": round(run["delay"]),
                    "confident": run["confident"],
                    "reported": reported,
                    "class": kind,
                    "subclass": subclass,
                    "offset_trips": offset_trips,
                    "offset_min": None if offset_min is None else round(offset_min, 1),
                    "ids": len(set(ids)),
                    "ids_include_best": best.trip_id in ids,
                    "first_change_frac": round(changes[0], 2) if changes else None,
                    "id_before_run": before[-1] if before else None,
                    "is_next_run": reported is not None
                    and next_best is not None
                    and reported == next_best.trip_id,
                    "reported_route": modal([r[6] for r in inside]),
                    "reported_direction": modal([r[7] for r in inside]),
                    "start_time_min_vs_best": None
                    if start_time is None
                    else round((start_time - best.first_dep) / 60, 1),
                    "start_time_min_vs_reported": None
                    if start_time is None or info is None
                    else round((start_time - info.first_dep) / 60, 1),
                }
            )
            previous_end = run["end"]
    mark_twins(out)
    return out


def mark_twins(runs: list[dict]) -> None:
    """Count the other vehicle ids that ran the same trip at the same time.

    A rail vehicle id names a set of cars, such as "1095-1100-1110", and on
    2026-11-13 route 801 had 83 ids for 229 trips. A twin is a run on the same
    route and direction, fitted to the same trip, overlapping in time. It is one
    train under two ids, or a fragment cut off by an id that changed.
    """
    groups = defaultdict(list)
    for run in runs:
        groups[(run["route"], run["direction"], run["best_trip"])].append(run)
    for rows in groups.values():
        for run in rows:
            twins = [o for o in rows if o["vehicle"] != run["vehicle"] and overlaps(run, o)]
            run["twins"] = len(twins)
            run["twin_same_reported"] = any(o["reported"] == run["reported"] for o in twins)


def quantiles(values: list) -> dict | None:
    if not values:
        return None
    ordered = sorted(values)
    pick = lambda q: ordered[min(len(ordered) - 1, int(q * len(ordered)))]  # noqa: E731
    return {"n": len(ordered), "p10": pick(0.1), "p50": pick(0.5), "p90": pick(0.9)}


def share(count: int, total: int) -> float:
    return round(100 * count / total, 1) if total else 0.0


def summarise(runs: list[dict], records: dict, scheduled: Counter) -> dict:
    out = {}
    for route in sorted({r["route"] for r in runs} | set(records)):
        mine = [r for r in runs if r["route"] == route]
        seen = {r["best_trip"] for r in mine}
        own = {r["best_trip"] for r in mine if r["ids_include_best"]}
        twinned = [r for r in mine if r["twins"]]
        entry = {
            "records": records.get(route),
            "runs": len(mine),
            "scheduled_trips": scheduled[route],
            "trips_with_a_run": len(seen),
            "trips_whose_own_id_was_reported": len(own),
            "runs_with_twin_pct": share(len(twinned), len(mine)),
            "twins_with_same_reported_pct": share(
                sum(1 for r in twinned if r["twin_same_reported"]), len(twinned)
            ),
            "vehicle_ids": len({r["vehicle"] for r in mine}),
        }
        for label, group in (("all", mine), ("confident", [r for r in mine if r["confident"]])):
            counts = Counter(r["class"] for r in group)
            entry[label] = {
                "runs": len(group),
                "classes": {
                    c: {"n": counts[c], "pct": share(counts[c], len(group))} for c in CLASSES
                },
                "not_in_force": dict(
                    Counter(
                        r["subclass"]
                        for r in group
                        if r["subclass"] and r["class"] == "not_in_force"
                    )
                ),
                "other_route": dict(
                    Counter(r["subclass"] for r in group if r["class"] == "other_route")
                ),
                "wrong_id_is_next_run": sum(
                    1 for r in group if r["is_next_run"] and r["class"] != "match"
                ),
                "offset_trips": {
                    str(k): v
                    for k, v in sorted(
                        Counter(
                            r["offset_trips"] for r in group if r["offset_trips"] is not None
                        ).items()
                    )
                },
                "offset_min": quantiles(
                    [r["offset_min"] for r in group if r["offset_min"] is not None]
                ),
                "ids_per_run": {
                    str(k): v for k, v in sorted(Counter(min(r["ids"], 4) for r in group).items())
                },
                "first_change_decile": {
                    str(k): v
                    for k, v in sorted(
                        Counter(
                            min(int(r["first_change_frac"] * 10), 9)
                            for r in group
                            if r["first_change_frac"] is not None
                        ).items()
                    )
                },
                "ids_include_best_pct": share(
                    sum(1 for r in group if r["ids_include_best"]), len(group)
                ),
                "id_before_run_equals_reported": sum(
                    1 for r in group if r["id_before_run"] and r["id_before_run"] == r["reported"]
                ),
                "reported_route_matches": share(
                    sum(1 for r in group if r["reported_route"] == r["route"]), len(group)
                ),
                "reported_direction_matches": share(
                    sum(1 for r in group if r["reported_direction"] == str(r["direction"])),
                    len(group),
                ),
                "start_time_within_2min_of_best": share(
                    sum(
                        1
                        for r in group
                        if r["start_time_min_vs_best"] is not None
                        and abs(r["start_time_min_vs_best"]) <= 2
                    ),
                    len(group),
                ),
                "start_time_within_2min_of_reported_trip": share(
                    sum(
                        1
                        for r in group
                        if r["start_time_min_vs_reported"] is not None
                        and abs(r["start_time_min_vs_reported"]) <= 2
                    ),
                    sum(1 for r in group if r["start_time_min_vs_reported"] is not None),
                ),
                "miss_s": quantiles([r["miss_s"] for r in group]),
            }
        out[route] = entry
    return out


def count_records(con) -> dict:
    """Rail records by reported route, and how many carry a latitude and longitude."""
    rows = con.execute(
        "SELECT coalesce(route_id, '(none)'), count(*), "
        "count(*) FILTER (WHERE lat IS NOT NULL AND lon IS NOT NULL) "
        "FROM rail GROUP BY 1 ORDER BY 1"
    ).fetchall()
    return {
        route: {"records": n, "with_position": pos, "with_position_pct": share(pos, n)}
        for route, n, pos in rows
    }


def run(service_date: str, files: list[str], timetable, out: Path) -> None:
    con = arrivals.connect()
    base = int(gtfs.day_base(service_date))
    con.execute(
        f"CREATE TABLE rail AS SELECT * FROM ({EXTRACT}) WHERE ts >= ? AND ts < ?",
        [files, RAIL_AGENCY, base + DAY_START_S, base + DAY_END_S],
    )
    records = count_records(con)
    reported = {
        row[0]
        for row in con.execute(
            "SELECT DISTINCT trip_id FROM rail WHERE start_date = ? AND trip_id IS NOT NULL",
            [service_date],
        ).fetchall()
    }
    directories, name = timetable(reported)
    trips, coords = load_timetable(directories, service_date)
    routes = build_routes(trips, coords)
    runs = analyse(con, trips, routes, base)

    out.mkdir(parents=True, exist_ok=True)
    summary = {
        "service_date": service_date,
        "timetable": name,
        "routes": summarise(runs, records, Counter(t.route for t in trips.values() if t.active)),
    }
    (out / f"rail_runs_{service_date}.json").write_text(json.dumps(summary, indent=2) + "\n")
    with (out / f"rail_runs_{service_date}.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(runs[0]) if runs else ["none"])
        writer.writeheader()
        writer.writerows(runs)
    print(f"{len(runs)} runs rebuilt for {service_date}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--service-date", required=True, help="YYYYMMDD")
    parser.add_argument("--cache", type=Path, help="raw file cache, required without --raw-dir")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--raw-dir", type=Path, help="read raw files from here, no bucket")
    parser.add_argument("--gtfs-dir", type=Path, help="an unpacked rail timetable, needs --raw-dir")
    args = parser.parse_args()

    if args.raw_dir:
        if not args.gtfs_dir:
            sys.exit("--raw-dir needs --gtfs-dir")
        files = arrivals.local_files(args.raw_dir, args.service_date)

        def timetable(_):
            return [args.gtfs_dir], str(args.gtfs_dir)

    else:
        if not args.cache or args.gtfs_dir:
            sys.exit("without --raw-dir, give --cache and no --gtfs-dir")
        client = Bucket()()
        files = arrivals.fetch_raw(client, args.service_date, args.cache)

        def timetable(reported):
            read: dict = {}
            chosen = gtfs.prepare(
                client, args.service_date, args.cache / "gtfs", {RAIL_AGENCY: reported}, read
            )[RAIL_AGENCY]
            others = [d for d in read.get(RAIL_AGENCY, []) if d != chosen]
            return [chosen, *others], chosen.name

    if not files:
        sys.exit(f"no raw files found for {args.service_date}")
    run(args.service_date, files, timetable, args.out)


if __name__ == "__main__":
    main()
