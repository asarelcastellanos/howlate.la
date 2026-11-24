"""Matches each rail vehicle's runs to the timetable by where the vehicle was and when.

The reported trip id is wrong on days when a line runs as split pieces (#177),
so a run is cut from latitude and longitude alone and fitted to the trips in
force. `pipeline/scripts/rail_runs.py` measures the reported id against this
fit, and `arrivals.match_rail_runs` grades with it.
"""

import bisect
import csv
import math
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from howlate_pipeline import gtfs
from howlate_pipeline.report import FIT_MARGIN, FIT_SECONDS, MIN_RUN_STOPS

RADIUS_M = 300
MAP_M = 300
MERGE_S = 600
GAP_S = 2400
MIN_STATIONS = 3
MIN_COMMON = 3
CONFIDENT_FIT_S = 120
CONFIDENT_MARGIN_S = 120
LAYOVER_S = 3600

# The one switch for grading rail by position. Off, every rail run is graded on
# the trip id it reported, as before the matcher. It ships off because it fell
# short of the threshold set on #178, which was 95% agreement with the reported
# id on every line with 30 or more trusted runs on a normal weekday. On
# 2026-11-13 and 11-20 the confident fits of trusted runs agreed in 91.6% to
# 100% of cases, and lines 801 (92.5% on 11-20), 804 (94.6%, 91.6%) and 805
# (92.7%, 93.9%) were under 95%. After the route tie-break and the misfit test,
# 801, 804 and 807 were still under 95% on 2026-11-18 or 11-19 with misfit ids set
# aside. Turn it on only after the owner reads those numbers on #178.
ENABLED = False

# How far a reported startTime may sit from its trip's first departure before the
# id is no longer trusted. On 2026-11-13 and 11-20, lines 802 to 807 had the
# startTime within 2 minutes of the reported trip's first departure in 100% of
# runs. On route 801 on 11-13 to 11-15 it was within 2 minutes in 13% to 17%.
TRUST_START_S = 120


@dataclass
class Trip:
    trip_id: str
    route: str
    direction: int | None
    service: str
    source: str
    active: bool
    later: bool
    weekday: bool
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


def load_timetable(directories: list[Path], service_date: str) -> tuple[dict, dict, dict]:
    """Every trip any copy lists, and every stop's coordinates and name.

    Only the first copy, the one grading uses, has running trips. A trip another
    copy adds is listed but never active, so the candidates for a fit are the
    timetable in force and nothing else. `weekday` is true for a later-start
    service whose calendar row runs on this date's weekday, which is the set a
    later timetable would offer if it were already in force.
    """
    trips: dict[str, Trip] = {}
    coords: dict[str, tuple[float, float]] = {}
    names: dict[str, str] = {}
    day = gtfs.DOW[datetime.strptime(service_date, "%Y%m%d").weekday()]
    for position, directory in enumerate(directories):
        active = gtfs.active_services(directory, service_date) if position == 0 else set()
        later = gtfs.later_start_services(directory, service_date)
        calendar = {r["service_id"]: r for r in read_rows(directory / "calendar.txt")}
        for row in read_rows(directory / "stops.txt"):
            try:
                coords.setdefault(row["stop_id"], (float(row["stop_lat"]), float(row["stop_lon"])))
                names.setdefault(row["stop_id"], row.get("stop_name", ""))
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
            service = row["service_id"]
            trips[trip_id] = Trip(
                trip_id,
                row["route_id"],
                int(direction) if direction.isdigit() else None,
                service,
                directory.name,
                service in active,
                service in later,
                service in later and calendar.get(service, {}).get(day) == "1",
                rows,
                rows[0][3],
            )
    return trips, coords, names


def metres(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dy = (lat2 - lat1) * 110540
    dx = (lon2 - lon1) * 111320 * math.cos(math.radians(lat1))
    return math.hypot(dx, dy)


def nearest(lat: float, lon: float, stations: list) -> tuple[int, float]:
    return min(
        ((k, metres(lat, lon, slat, slon)) for k, (slat, slon) in enumerate(stations)),
        key=lambda pair: pair[1],
    )


def map_trip(trip: Trip, stations: list, coords: dict) -> dict:
    """The trip's times by reference station, matched by coordinates."""
    mapped = {}
    for _, stop_id, arr, dep in trip.stops:
        if stop_id in coords:
            k, dist = nearest(*coords[stop_id], stations)
            if dist <= MAP_M:
                mapped.setdefault(k, (arr, dep))
    return mapped


def build_routes(trips: dict, coords: dict) -> dict:
    """The reference station lists, one for each stop pattern of each running route.

    A route can run as separate pieces. On 2026-11-13 the timetable in force
    split route 801 into a 13 stop trip from Downtown Long Beach and a 30 stop
    trip to Pomona North, with 117 trips each way in each piece. One list from
    the longest trip would hold only one piece and leave the other without runs.
    So trips are taken longest first, and a trip with under half its stops
    within MAP_M of any list so far starts a new list, keyed "801#2". Every trip
    is mapped onto its list by coordinates, not by stop_id, because the two
    directions can use different platform ids at one station.

    `later_fits` holds the later-start trips that run on this weekday, mapped
    onto the same stations, so a fit to them tests the times and not the pattern.
    """
    by_route = defaultdict(list)
    for trip in trips.values():
        if trip.active and trip.direction is not None:
            by_route[trip.route].append(trip)
    routes: dict = {}
    for route, listed in by_route.items():
        for trip in sorted(listed, key=lambda t: (-len(t.stops), t.trip_id)):
            best = None
            for key, info in routes.items():
                if info["route"] == route:
                    mapped = map_trip(trip, info["stations"], coords)
                    if best is None or len(mapped) > len(best[1]):
                        best = (key, mapped)
            if best is None or 2 * len(best[1]) < len(trip.stops):
                count = sum(1 for info in routes.values() if info["route"] == route)
                key = route if not count else f"{route}#{count + 1}"
                stations = [coords[s[1]] for s in trip.stops if s[1] in coords]
                routes[key] = {
                    "route": route,
                    "stations": stations,
                    "ref_direction": trip.direction,
                    "fits": defaultdict(list),
                    "later_fits": defaultdict(list),
                }
                best = (key, map_trip(trip, stations, coords))
            routes[best[0]]["fits"][trip.direction].append((trip, best[1]))
    for trip in trips.values():
        if trip.weekday and trip.direction is not None:
            for info in routes.values():
                if info["route"] == trip.route:
                    mapped = map_trip(trip, info["stations"], coords)
                    if len(mapped) >= MIN_COMMON:
                        info["later_fits"][trip.direction].append((trip, mapped))
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


def vehicle_runs(samples: list, routes: dict, reported=None) -> list[dict]:
    """The runs of one vehicle, each route's candidates pruned by stations explained.

    Two routes can share track, and a run on it is explained by both station
    lists with the same number of stations. `reported(start, end)`, when given,
    returns the routeId the vehicle's records carried in that window, and breaks
    such a tie toward that route. It never overrides a list that explains more
    stations. On 2026-11-13 and 11-20, 20 of the 21 confident 805 runs that
    disagreed with a reported id were labelled with route 802 or 804 by the feed
    and fitted to 805.
    """
    candidates = []
    for key, info in routes.items():
        for sign, run in split_runs(stretches(samples, info["stations"])):
            direction = info["ref_direction"] if sign > 0 else 1 - info["ref_direction"]
            times = {run[0].k: run[0].last, run[-1].k: run[-1].first}
            times.update({s.k: s.best for s in run[1:-1]})
            candidates.append(
                {
                    "route": info["route"],
                    "ref": key,
                    "direction": direction,
                    "start": run[0].last,
                    "end": run[-1].first,
                    "times": times,
                    "origin": run[0].k,
                    "stations": len(run),
                }
            )
    chosen: list[dict] = []

    def rank(run):
        route = reported(run["start"], run["end"]) if reported else None
        return (-run["stations"], route is not None and route != run["route"])

    for run in sorted(candidates, key=rank):
        if not any(overlaps(run, other) for other in chosen):
            chosen.append(run)
    return sorted(chosen, key=lambda r: r["start"])


def residuals(run: dict, mapped: dict, base: int) -> list[int]:
    """Seconds the run was late at each station it shares with a trip, signed."""
    return [
        ts - base - (mapped[k][1] if k == run["origin"] else mapped[k][0])
        for k, ts in run["times"].items()
        if k in mapped
    ]


def fit_run(run: dict, candidates: list, base: int) -> dict:
    """Fit a run to each candidate trip, as (trip, mapped stations)."""
    scored = []
    for trip, mapped in candidates:
        signed = residuals(run, mapped, base)
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
        "misses": {row[3].trip_id: row[0] for row in scored},
    }


def modal(values: list):
    counts = Counter(v for v in values if v is not None)
    return counts.most_common(1)[0][0] if counts else None


@dataclass
class Decision:
    """What the grader does with one run, and the evidence for it.

    `trip` is the trip the run is graded against, the reported one when trusted
    and the fitted one when matched. `fit` is kept for a trusted run too, so a
    script can compare the two.
    """

    vehicle: str
    run: dict
    reported: str | None
    outcome: str
    trip: Trip | None
    fit: dict
    looks_trusted: bool = False
    misfit: bool = False


def trusts(trip: Trip | None, start_time: int | None) -> bool:
    """Whether a reported id checks out against the timetable in force.

    The trip must run today and the reported startTime must agree with its first
    departure. A missing startTime cannot agree. Both signals can be stale
    together, so a stale id that carries a stale startTime passes this.
    """
    return (
        trip is not None
        and trip.active
        and start_time is not None
        and abs(start_time - trip.first_dep) <= TRUST_START_S
    )


def is_misfit(fit: dict, reported: str | None) -> bool:
    """The rule `report.rail_misfits` uses, on the run's own station times.

    Another trip of the run's piece and direction fits within FIT_SECONDS and the
    reported trip is FIT_MARGIN or more worse. A reported trip outside that piece
    and direction, or a run with too few stations in common, cannot be judged.
    On 2026-11-13 and 11-20, 28 of the 86 confident 801, 804 and 805 runs whose
    id and startTime agreed but whose fit was another trip met it.
    """
    miss = fit.get("misses", {}).get(reported)
    others = [m for trip, m in fit.get("misses", {}).items() if trip != reported]
    return (
        miss is not None
        and fit["common"] > MIN_RUN_STOPS
        and bool(others)
        and min(others) <= FIT_SECONDS
        and miss - min(others) >= FIT_MARGIN
    )


def decide_vehicle(
    vehicle: str, records: list, trips: dict, routes: dict, base: int
) -> list[Decision]:
    """Every run of one vehicle with its outcome.

    `records` are (vehicle_id, ts, lat, lon, trip_id, start_time, route_id) in
    time order. A run is trusted when its most common reported id checks out and
    the run is not a misfit, else matched when its fit is confident, else
    ungraded.
    """
    samples = [(r[1], r[2], r[3]) for r in records if r[2] is not None and r[3] is not None]
    stamps = [r[1] for r in records]
    decisions = []

    def reported_route(start, end):
        inside = records[bisect.bisect_left(stamps, start) : bisect.bisect_right(stamps, end)]
        return modal([r[6] for r in inside])

    for run in vehicle_runs(samples, routes, reported_route):
        fit = fit_run(run, routes[run["ref"]]["fits"][run["direction"]], base)
        inside = records[
            bisect.bisect_left(stamps, run["start"]) : bisect.bisect_right(stamps, run["end"])
        ]
        reported = modal([r[4] for r in inside])
        looks_trusted = trusts(trips.get(reported), clock(modal([r[5] for r in inside])))
        misfit = looks_trusted and is_misfit(fit, reported)
        if looks_trusted and not misfit:
            outcome, trip = "trusted", trips[reported]
        elif fit["best"] is not None and fit["confident"]:
            outcome, trip = "matched", fit["best"]
        else:
            outcome, trip = "ungraded", None
        decisions.append(
            Decision(vehicle, run, reported, outcome, trip, fit, looks_trusted, misfit)
        )
    return decisions


def decide(rows: list, trips: dict, routes: dict, base: int) -> dict[str, list[Decision]]:
    """The decisions for every vehicle in `rows`, keyed by vehicle id."""
    by_vehicle = defaultdict(list)
    for row in rows:
        by_vehicle[row[0]].append(row)
    return {
        vehicle: decide_vehicle(vehicle, records, trips, routes, base)
        for vehicle, records in by_vehicle.items()
    }


def segments(decisions: list[Decision]) -> list[tuple]:
    """Cut one vehicle's time into stretches that each belong to one run.

    Returns (vehicle, first second, last second, status or None, outcome, trip).
    A run owns its own seconds. Its trip's last approach reports come after the
    run ends and before the next run starts, and the STOPPED_AT reports of its
    origin come before it starts, because a rail vehicle waits at the terminal
    that ends one run and starts the next. So the approach reports after a run
    belong to it, for up to GAP_S, and the stopped reports before it belong to
    it, for up to LAYOVER_S. The two never share a second, and a second inside
    two runs that overlap goes to the earlier one.
    """
    found = []
    previous_end = None
    for i, d in enumerate(decisions):
        run = d.run
        following = decisions[i + 1].run["start"] if i + 1 < len(decisions) else None
        end = run["end"] if following is None else min(run["end"], following - 1)
        trip = d.trip.trip_id if d.outcome == "matched" else None
        tail = end + GAP_S if following is None else min(following - 1, end + GAP_S)
        head = run["start"] - LAYOVER_S
        if previous_end is not None:
            head = max(head, previous_end + 1)
        for lo, hi, status in (
            (run["start"], end, None),
            (end + 1, tail, "IN_TRANSIT_TO"),
            (head, run["start"] - 1, "STOPPED_AT"),
        ):
            if lo <= hi:
                found.append((d.vehicle, lo, hi, status, d.outcome, trip))
        previous_end = end
    return found
