"""Size the v0.6.0 commute route files and check that each bus service has one day type.

Follows the contract for `backfill-vm.sh --script`:

    python <script> --service-date YYYYMMDD --cache DIR --out DIR

For the 56 service days ending at --service-date it reads the graded arrivals
and trips from gs://howlate-derived (Standard storage, same region as the VM)
and the timetable the grader would pick for each day from gs://howlate-raw/gtfs/.
It never reads vehicle_positions/. Writes OUT/commute_sizing_DAY.json.

--derived DIR reads arrivals/v2 and trips/v2 from a local folder instead, and
--gtfs-dir DIR uses the bus timetable in DIR for every day. Together they run
the script with no network, for a fixture.

A departure pattern is a bus line, direction, day type and scheduled start, which
is the trip's first scheduled_time in seconds after the service day began, so a
trip past midnight stays on the day it started. Only measured rows count, and a
trip's start comes from all of its rows so a missing first stop cannot move it.
"""

import argparse
import csv
import gzip
import json
import math
import re
import resource
import statistics
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from howlate_pipeline import BUS_AGENCY, DERIVED_BUCKET, arrivals, gtfs  # noqa: E402
from howlate_pipeline.__main__ import Bucket  # noqa: E402

WINDOW = 56
DAY_TYPES = ["weekday", "saturday", "sunday"]
MEASURED = "r.source NOT IN ('none', 'interpolated')"


def window_days(last: str) -> list[str]:
    end = datetime.strptime(last, "%Y%m%d")
    return [(end - timedelta(days=n)).strftime("%Y%m%d") for n in range(WINDOW - 1, -1, -1)]


def weekday_type(service_date: str) -> str:
    weekday = datetime.strptime(service_date, "%Y%m%d").weekday()
    return DAY_TYPES[0 if weekday < 5 else weekday - 4]


def row_types(row: dict) -> set[str]:
    found = set()
    if any(row[name] == "1" for name in gtfs.DOW[:5]):
        found.add("weekday")
    if row["saturday"] == "1":
        found.add("saturday")
    if row["sunday"] == "1":
        found.add("sunday")
    return found


def mask(row: dict) -> str:
    return "".join(
        letter if row[name] == "1" else "-"
        for letter, name in zip("MTWTFSS", gtfs.DOW, strict=True)
    )


def read_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def services_on(directory: Path, service_date: str) -> dict:
    """What S1 needs from one day's timetable: the active services and their weekdays."""
    with_trips = {row["service_id"] for row in read_rows(directory / "trips.txt")}
    active = gtfs.active_services(directory, service_date)
    rows = [
        row
        for row in read_rows(directory / "calendar.txt")
        if row["service_id"] in active and row["start_date"] <= service_date <= row["end_date"]
    ]
    listed = {row["service_id"] for row in rows}
    running = active & with_trips
    types: dict[str, set[str]] = {}
    masks: dict[str, set[str]] = {}
    for row in rows:
        if row["service_id"] in running:
            types.setdefault(row["service_id"], set()).update(row_types(row))
            masks.setdefault(row["service_id"], set()).add(mask(row))
    return {
        "active": len(active),
        "running": len(running),
        "calendar_dates_only": sorted(running - listed),
        "types": types,
        "masks": masks,
    }


def settle_s1(days: list[str], found: dict[str, dict]) -> tuple[dict, dict[str, str]]:
    per_service: dict[str, dict] = {}
    per_day = []
    day_type: dict[str, str] = {}
    only_dates: dict[str, int] = {}
    for day in days:
        info = found[day]
        for service, kinds in info["types"].items():
            entry = per_service.setdefault(service, {"types": set(), "masks": set(), "dates": 0})
            entry["types"] |= kinds
            entry["masks"] |= info["masks"][service]
            entry["dates"] += 1
        for service in info["calendar_dates_only"]:
            only_dates[service] = only_dates.get(service, 0) + 1
        kinds = set().union(*info["types"].values()) if info["types"] else set()
        calendar_type = weekday_type(day)
        day_type[day] = next(iter(kinds)) if len(kinds) == 1 else calendar_type
        per_day.append(
            {
                "date": day,
                "weekday": calendar_type,
                "services_active": info["active"],
                "services_with_trips": info["running"],
                "types": sorted(kinds),
                "day_type_used": day_type[day],
                "calendar_dates_only": len(info["calendar_dates_only"]),
            }
        )
    many = {
        service: {
            "types": sorted(entry["types"]),
            "masks": sorted(entry["masks"]),
            "dates_active": entry["dates"],
        }
        for service, entry in sorted(per_service.items())
        if len(entry["types"]) > 1
    }
    unresolved = [row["date"] for row in per_day if len(row["types"]) != 1]
    return {
        "services_run": len(per_service),
        "services_on_more_than_one_day_type": len(many),
        "multi_type_services": many,
        "dates_not_one_day_type": len(unresolved),
        "dates_not_one_day_type_list": unresolved,
        "calendar_dates_only_services": dict(sorted(only_dates.items())),
        "per_date": per_day,
    }, day_type


def fetch_inputs(days: list[str], cache: Path, derived: Path | None, gtfs_dir: Path | None):
    """Local paths of each day's arrivals and trips, and its bus timetable."""
    client = None if derived else Bucket()()
    arrival_files, directories = [], {}
    for day in days:
        paths = {}
        for table in ("arrivals", "trips"):
            relative = arrivals.partition(table, day) + "part-0.parquet"
            if derived:
                path = derived / relative
                if not path.exists():
                    sys.exit(f"{path} is missing, so {day} was never graded")
            else:
                path = cache / "derived" / relative
                blob = client.bucket(DERIVED_BUCKET).get_blob(relative)
                if blob is None:
                    sys.exit(
                        f"gs://{DERIVED_BUCKET}/{relative} is missing, so {day} was never graded"
                    )
                path.parent.mkdir(parents=True, exist_ok=True)
                blob.download_to_filename(path)
            paths[table] = path
        arrival_files.append(str(paths["arrivals"]))
        if gtfs_dir:
            directories[day] = gtfs_dir
            continue
        con = arrivals.connect()
        seen: dict[str, set[str]] = {}
        for agency, trip_id in con.execute(
            "SELECT DISTINCT agency, trip_id FROM read_parquet(?) WHERE reports > 0",
            [str(paths["trips"])],
        ).fetchall():
            seen.setdefault(agency, set()).add(trip_id)
        directories[day] = gtfs.prepare(client, day, cache / "gtfs", seen)[BUS_AGENCY]
    return arrival_files, directories


def stop_list(directory: Path) -> list[list]:
    return [
        [
            row["stop_id"],
            row["stop_name"],
            round(float(row["stop_lat"]), 6),
            round(float(row["stop_lon"]), 6),
        ]
        for row in read_rows(directory / "stops.txt")
    ]


ENCODINGS = {
    "abs_1s": (1, "abs"),
    "abs_10s": (10, "abs"),
    "delta_stops_1s": (1, "delta"),
    "delta_stops_10s": (10, "delta"),
    "resid_median_1s": (1, "resid"),
    "resid_median_10s": (10, "resid"),
}
LIMIT = 300_000
BATCH_ROWS = 5_000_000
DUCKDB_MEMORY = "3GB"


def peak_bytes() -> int:
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak if sys.platform == "darwin" else peak * 1024


def sized(payload) -> dict:
    raw = json.dumps(payload, separators=(",", ":")).encode()
    return {
        "raw": len(raw),
        "gzip6": len(gzip.compress(raw, 6)),
        "gzip9": len(gzip.compress(raw, 9)),
    }


def encode(unit: int, mode: str, grid: list[list]) -> tuple[list, list]:
    """One pattern's grid, a row per stop and a column per day, as (bases, rows).

    abs keeps each time in seconds after the pattern's start. delta subtracts,
    for each day, the last time that day at an earlier stop, so a row is the ride
    time from the stop before. resid subtracts the stop's median across days and
    keeps that median as the base. Units of 10 seconds round before any subtraction.
    """
    rows = [[None if v is None else round(v / unit) for v in row] for row in grid]
    if mode == "abs":
        return [], rows
    if mode == "delta":
        previous = [0] * (len(rows[0]) if rows else 0)
        out = []
        for row in rows:
            out.append([None if v is None else v - previous[j] for j, v in enumerate(row)])
            previous = [previous[j] if v is None else v for j, v in enumerate(row)]
        return [], out
    bases = [statistics.median_low([v for v in row if v is not None]) for row in rows]
    return bases, [
        [None if v is None else v - base for v in row]
        for base, row in zip(bases, rows, strict=True)
    ]


def file_sizes(rows: list) -> tuple[dict, int]:
    """Sizes of one route file, per direction and day type, in every encoding."""
    stops: dict[str, int] = {}
    patterns: dict[int, dict] = {}
    for start, seq, stop, day, rel in rows:
        index = stops.setdefault(stop, len(stops))
        pattern = patterns.setdefault(start, {"days": set(), "cells": {}})
        pattern["days"].add(day)
        pattern["cells"].setdefault((seq, index), {})[day] = rel
    prepared = []
    for start, pattern in patterns.items():
        order = sorted(pattern["days"])
        cells = sorted(pattern["cells"].items())
        grid = [[values.get(day) for day in order] for _, values in cells]
        prepared.append((start, order, [index for (_, index), _ in cells], grid))
    result = {}
    for name, (unit, mode) in ENCODINGS.items():
        packed = []
        for start, order, ids, grid in prepared:
            bases, matrix = encode(unit, mode, grid)
            packed.append([start, order, ids, bases, matrix])
        result[name] = sized([list(stops), packed])
    return result, len(patterns)


def quantile(values: list[int], share: float) -> int:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(share * len(ordered)) - 1)]


def summarise(files: list[dict]) -> dict:
    summary = {}
    for name in ENCODINGS:
        entry = {}
        for metric in ("raw", "gzip6", "gzip9"):
            values = [row["sizes"][name][metric] for row in files]
            entry[metric] = {
                "max": max(values),
                "p95": quantile(values, 0.95),
                "median": statistics.median(values),
            }
        entry["files_over_limit_gzip6"] = [
            {k: row[k] for k in ("line", "direction", "day_type")}
            | {"gzip6": row["sizes"][name]["gzip6"]}
            for row in sorted(files, key=lambda row: -row["sizes"][name]["gzip6"])
            if row["sizes"][name]["gzip6"] > LIMIT
        ]
        summary[name] = entry
    return summary


def run(service_date: str, cache: Path, out: Path, derived: Path | None, gtfs_dir: Path | None):
    days = window_days(service_date)
    started = time.perf_counter()
    files, directories = fetch_inputs(days, cache, derived, gtfs_dir)
    fetched = time.perf_counter() - started

    found = {day: services_on(directories[day], day) for day in days}
    s1, day_type = settle_s1(days, found)

    con = arrivals.connect()
    con.execute(f"SET memory_limit = '{DUCKDB_MEMORY}'")
    stage = time.perf_counter()
    con.execute(
        "CREATE TABLE days (day_idx INTEGER, service_date VARCHAR, base BIGINT, daytype VARCHAR)"
    )
    con.executemany(
        "INSERT INTO days VALUES (?, ?, ?, ?)",
        [(i, day, int(gtfs.day_base(day)), day_type[day]) for i, day in enumerate(days)],
    )
    line_rows = con.execute(
        "SELECT line, count(*) FROM read_parquet(?, hive_partitioning = false) "
        f"WHERE agency = '{BUS_AGENCY}' GROUP BY line ORDER BY line",
        [files],
    ).fetchall()
    batches, current, total = [], [], 0
    for line, count in line_rows:
        if current and total + count > BATCH_ROWS:
            batches.append(current)
            current, total = [], 0
        current.append(line)
        total += count
    if current:
        batches.append(current)

    results, per_route, batch_log = [], {}, []
    for batch in batches:
        quoted = ", ".join("'" + line.replace("'", "''") + "'" for line in batch)
        for table in ("bus", "m"):
            con.execute(f"DROP TABLE IF EXISTS {table}")
        con.execute(
            f"""
            CREATE TABLE bus AS
            SELECT d.day_idx, r.line, r.direction_id, r.trip_id, r.stop_id, r.stop_sequence,
                   CAST(epoch(r.scheduled_time) AS BIGINT) - d.base AS sched_off,
                   CAST(epoch(r.actual_time) AS BIGINT) - d.base AS act_off,
                   r.delay_seconds, {MEASURED} AS measured
            FROM (
                SELECT line, direction_id, trip_id, stop_id, stop_sequence, scheduled_time,
                       actual_time, delay_seconds, source,
                       regexp_replace(regexp_extract(filename, 'service_date=([0-9-]{{10}})', 1), '-', '', 'g') AS day
                FROM read_parquet(?, filename = true, hive_partitioning = false)
                WHERE agency = '{BUS_AGENCY}' AND line IN ({quoted})
            ) r JOIN days d ON d.service_date = r.day
            """,
            [files],
        )
        con.execute(
            """
            CREATE TABLE m AS
            SELECT b.day_idx, d.daytype, b.line, b.direction_id, t.start_s, b.stop_sequence,
                   b.stop_id, b.act_off - t.start_s AS rel
            FROM bus b
            JOIN (SELECT day_idx, trip_id, min(sched_off) AS start_s FROM bus GROUP BY ALL) t
              USING (day_idx, trip_id)
            JOIN days d USING (day_idx)
            WHERE b.measured
            """
        )
        con.execute("DROP TABLE bus")
        for line, direction, kind in con.execute(
            "SELECT DISTINCT line, direction_id, daytype FROM m ORDER BY ALL"
        ).fetchall():
            rows = con.execute(
                "SELECT start_s, stop_sequence, stop_id, day_idx, min(rel) FROM m "
                "WHERE line = ? AND direction_id = ? AND daytype = ? GROUP BY ALL ORDER BY ALL",
                [line, direction, kind],
            ).fetchall()
            sizes, count = file_sizes(rows)
            per_route.setdefault(kind, {}).setdefault(line, 0)
            per_route[kind][line] += count
            results.append(
                {
                    "line": line,
                    "direction": direction,
                    "day_type": kind,
                    "patterns": count,
                    "cells": len(rows),
                    "sizes": sizes,
                }
            )
        batch_log.append({"lines": len(batch), "peak_bytes": peak_bytes()})

    patterns = {}
    for kind in DAY_TYPES:
        counts = per_route.get(kind, {})
        patterns[kind] = {
            "patterns": sum(counts.values()),
            "routes": len(counts),
            "per_route_median": statistics.median(counts.values()) if counts else None,
            "per_route_max": max(counts.values()) if counts else None,
        }
    elapsed = round(time.perf_counter() - stage, 1)

    stops = stop_list(directories[days[-1]])
    result = {
        "service_date": service_date,
        "first_day": days[0],
        "days": len(days),
        "s1": s1,
        "lines": len(line_rows),
        "files": len(results),
        "limit_bytes": LIMIT,
        "patterns_per_day_type": patterns,
        "summary": summarise(results),
        "stop_list": {"stops": len(stops), **sized(stops)},
        "run": {
            "fetch_seconds": round(fetched, 1),
            "build_seconds": elapsed,
            "batches": batch_log,
            "peak_bytes_process": peak_bytes(),
            "duckdb_memory_limit": DUCKDB_MEMORY,
        },
        "per_file": results,
    }
    out.mkdir(parents=True, exist_ok=True)
    target = out / f"commute_sizing_{service_date}.json"
    partial = target.with_suffix(".tmp")
    try:
        partial.write_text(json.dumps(result, indent=2) + "\n")
        partial.replace(target)
    finally:
        partial.unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--service-date", required=True, help="YYYYMMDD")
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--derived", type=Path, help="local folder holding arrivals/v2 and trips/v2"
    )
    parser.add_argument("--gtfs-dir", type=Path, help="bus timetable used for every day")
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9]{8}", args.service_date):
        sys.exit(f"--service-date {args.service_date} is not YYYYMMDD")
    datetime.strptime(args.service_date, "%Y%m%d")
    if bool(args.derived) != bool(args.gtfs_dir):
        sys.exit("--derived and --gtfs-dir go together")
    run(args.service_date, args.cache, args.out, args.derived, args.gtfs_dir)
