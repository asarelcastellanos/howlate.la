"""The commute files: each bus trip's time at each stop, for the last 56 service days.

The commute page answers "which bus, how long, how late" for two stops on one bus
route. Ride time must come from the same trip, so each file keeps each day's time
at each stop and not a spread. ADR-0004 gives the layout and the size limit.

A departure pattern is a bus line, direction, day type and scheduled start. The
start is the trip's first scheduled_time, in seconds after the service day's base
instant (gtfs.day_base). Trips of two timetable versions that start at the same
time on the same kind of day are one pattern, whatever their trip ids. When two
trips of one day start at the same time, only the one with more measured rows is
kept, so a day's column never mixes two trips and a ride time stays from one trip. A trip
past midnight stays with the service day it started on, because the day comes
from the arrivals row's service_date and never from a clock. Only measured bus
rows count: source `none` and `interpolated` are left out, and rail is too.

The day type of a service date comes from the timetable in force that day. The
bus services that run on it are read from calendar.txt and calendar_dates.txt,
and the date is a weekday, Saturday or Sunday when every one of them has a
calendar row for that kind of day only. A date that resolves to no type or to
more than one is left out and named in the log, because guessing from the
calendar would put its trips in the wrong pattern. On the 56 days ending
2026-11-23 every date resolved.

Files, under the site run folder:

    commute/index.json
        {"first_day", "last_day", "days", "unit": 10, "stops": "commute/stops.json",
         "files": [{"line", "direction", "day_type", "file", "patterns", "days"}]}
    commute/stops.json
        [[stop_id, name, lat, lon], ...] for every bus stop, sorted by id
    commute/<line>-<direction>-<day_type>.json
        {"line", "direction", "day_type", "days": ["YYYYMMDD", ...], "stops": [stop_id, ...],
         "patterns": [[start, day_indexes, stop_indexes, rows, scheduled], ...]}

`days` holds the service dates of that day type in the window, oldest first. In a
pattern, `start` is whole seconds and `day_indexes` lists the entries of `days`
the pattern ran on. `stop_indexes` lists the entries of `stops` the pattern
serves, in stop_sequence order, and `rows` has one row per stop with one entry
per day index, null where that day has no measured time at that stop.

An entry is a number of 10 second units, as a whole number. It is the change from
the same day's time at the last earlier stop that has one, and from the pattern's
start for the first. Each time is rounded to a unit before the change is taken,
so a time is off by up to 5 seconds and a ride time by up to 10. To read a day's
time at stop k, add the entries of that day's column down to row k, skipping
nulls, and multiply by 10.

A stop is one entry of `stop_indexes` per visit within a trip, so a stop that a
timetable version numbers differently is still one entry, and a stop a trip
passes twice is two. Entries run in order of scheduled offset, then stop_sequence.

`scheduled` has one entry per entry of `stop_indexes`, in the same order. It is
the timetable's time at that stop in seconds after the pattern's `start`, rounded
to a unit and coded as the change from the stop before in the list, and from 0
for the first, so the sum of the entries down to k, times 10, is the scheduled
offset at stop k. Where two timetable versions of one pattern differ, the
earlier offset is kept. A stop is listed only if some day measured it, so the
change can span stops the pattern also serves but nobody measured.

A file may not pass LIMIT bytes gzipped at level 6. `build` returns the files
that do, and the daily job fails the day on any. ADR-0004 measured the largest
file at 411,809 bytes over 56 days.
"""

import csv
import gzip
import re
import statistics
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

import duckdb

from howlate_pipeline import BUS_AGENCY, gtfs
from howlate_pipeline.aggregate import write_json

WINDOW = 56
UNIT = 10
LIMIT = 450_000
DAY_TYPES = ["weekday", "saturday", "sunday"]
BATCH_ROWS = 5_000_000
SAFE_NAME = re.compile(r"[A-Za-z0-9_-]+")
MEASURED = "source NOT IN ('none', 'interpolated')"

DAY_SQL = "regexp_replace(CAST(service_date AS VARCHAR), '-', '', 'g')"


def window(last: str) -> list[str]:
    """The 56 service days ending with `last` (YYYYMMDD), oldest first."""
    end = datetime.strptime(last, "%Y%m%d")
    return [(end - timedelta(days=n)).strftime("%Y%m%d") for n in range(WINDOW - 1, -1, -1)]


def graded_days(arrivals_dir: Path, last: str) -> list[str]:
    """The days of the window that have graded arrivals, oldest first."""
    return [
        day
        for day in window(last)
        if any((arrivals_dir / f"service_date={day[:4]}-{day[4:6]}-{day[6:]}").glob("*.parquet"))
    ]


def window_files(arrivals_dir: Path, last: str) -> list[str]:
    found = []
    for day in graded_days(arrivals_dir, last):
        folder = arrivals_dir / f"service_date={day[:4]}-{day[4:6]}-{day[6:]}"
        found += sorted(str(path) for path in folder.glob("*.parquet"))
    return found


def day_types(days: list[str], directory_for: Callable[[str], Path]) -> dict[str, str]:
    """The day type of each date that has one, from the timetable `directory_for` names.

    A date whose timetable cannot be fetched or read is left out and logged, because
    one bad copy must not stop the line files or the other 55 days.
    """
    types = {}
    for day in days:
        try:
            kind = day_type(directory_for(day), day)
        except (Exception, SystemExit) as error:
            reason = (str(error).splitlines() or [""])[0]
            print(
                f"  commute: {day} left out, its timetable could not be read: {type(error).__name__} {reason}"
            )
            continue
        if kind is None:
            print(f"  commute: {day} has no single day type in its timetable, left out")
        else:
            types[day] = kind
    return types


def day_type(directory: Path, service_date: str) -> str | None:
    """The day type of one service date from the timetable in force, or None.

    Reads the services that run that day, which `gtfs.active_services` already
    settles from calendar.txt and calendar_dates.txt, and takes the kinds of day
    their calendar rows are for. A service added only by calendar_dates has no
    row and says nothing. A service with no trips says nothing either.
    """

    def read(name: str) -> list[dict]:
        with (directory / name).open(encoding="utf-8-sig") as handle:
            return list(csv.DictReader(handle))

    running = gtfs.active_services(directory, service_date) & {
        row["service_id"] for row in read("trips.txt")
    }
    kinds: set[str] = set()
    for row in read("calendar.txt"):
        if row["service_id"] in running and row["start_date"] <= service_date <= row["end_date"]:
            if any(row[name] == "1" for name in gtfs.DOW[:5]):
                kinds.add("weekday")
            if row["saturday"] == "1":
                kinds.add("saturday")
            if row["sunday"] == "1":
                kinds.add("sunday")
    return next(iter(kinds)) if len(kinds) == 1 else None


def observed_trips(con: duckdb.DuckDBPyConnection, files: list[str]) -> dict[str, set[str]]:
    """The bus trip_ids with a report, by service day, which `gtfs.prepare` matches copies against."""
    found: dict[str, set[str]] = {}
    for day, trip_id in con.execute(
        f"SELECT DISTINCT {DAY_SQL}, trip_id FROM read_parquet(?, hive_partitioning = false) "
        f"WHERE agency = '{BUS_AGENCY}' AND source != 'none'",
        [files],
    ).fetchall():
        found.setdefault(day, set()).add(trip_id)
    return found


def load(
    con: duckdb.DuckDBPyConnection,
    files: list[str],
    types: dict[str, str],
    lines: list[str] | None = None,
) -> None:
    """Make table `m`: one row per measured bus stop time on a day that has a day type.

    `types` maps each service date to its day type, and a date missing from it is
    left out. `lines` limits the read to those lines.
    """
    for table in ("days", "bus", "m"):
        con.execute(f"DROP TABLE IF EXISTS {table}")
    con.execute("CREATE TABLE days (service_date VARCHAR, base BIGINT, daytype VARCHAR)")
    con.executemany(
        "INSERT INTO days VALUES (?, ?, ?)",
        [(day, int(gtfs.day_base(day)), kind) for day, kind in sorted(types.items())],
    )
    only = ""
    if lines is not None:
        only = (
            "AND line IN (" + ", ".join("'" + line.replace("'", "''") + "'" for line in lines) + ")"
        )
    con.execute(
        f"""
        CREATE TABLE bus AS
        SELECT d.service_date AS day, d.daytype, r.line, r.direction_id, r.trip_id, r.stop_id,
               r.stop_sequence,
               row_number() OVER (
                   PARTITION BY d.service_date, r.trip_id, r.stop_id ORDER BY r.stop_sequence
               ) - 1 AS visit,
               CAST(epoch(r.scheduled_time) AS BIGINT) - d.base AS sched_off,
               CAST(epoch(r.actual_time) AS BIGINT) - d.base AS act_off,
               {MEASURED} AS measured
        FROM (
            SELECT {DAY_SQL} AS day, line, direction_id, trip_id, stop_id, stop_sequence,
                   scheduled_time, actual_time, source
            FROM read_parquet(?, hive_partitioning = false)
            WHERE agency = '{BUS_AGENCY}' {only}
        ) r JOIN days d ON d.service_date = r.day
        """,
        [files],
    )
    con.execute(
        """
        CREATE TABLE m AS
        SELECT b.day, b.daytype, b.line, b.direction_id, t.start_s, b.stop_sequence, b.stop_id, b.visit,
               b.act_off - t.start_s AS rel, b.sched_off - t.start_s AS sched_rel
        FROM bus b
        JOIN (
            SELECT day, trip_id, start_s FROM (
                SELECT day, trip_id, min(sched_off) AS start_s,
                       count(*) FILTER (WHERE measured) AS seen
                FROM bus GROUP BY ALL
            )
            QUALIFY row_number() OVER (
                PARTITION BY day, start_s ORDER BY seen DESC, trip_id
            ) = 1
        ) t USING (day, trip_id)
        WHERE b.measured
        """
    )
    con.execute("DROP TABLE bus")


def patterns(con: duckdb.DuckDBPyConnection) -> list[tuple]:
    """Every departure pattern in `m`, as (line, direction, day type, start), sorted."""
    return con.execute(
        "SELECT DISTINCT line, direction_id, daytype, start_s FROM m ORDER BY ALL"
    ).fetchall()


def encode(grid: list[list]) -> list[list]:
    """One pattern's times, a row per stop and an entry per day, as changes in 10 second units."""
    previous = [0] * (len(grid[0]) if grid else 0)
    rows = []
    for row in grid:
        units = [None if v is None else round(v / UNIT) for v in row]
        rows.append([None if u is None else u - previous[i] for i, u in enumerate(units)])
        previous = [previous[i] if u is None else u for i, u in enumerate(units)]
    return rows


def route_file(
    con: duckdb.DuckDBPyConnection, line: str, direction: int, kind: str, days: list[str]
) -> dict:
    """The file for one line, direction and day type, from table `m`."""
    own = {day: index for index, day in enumerate(days)}
    stops: dict[str, int] = {}
    found: dict[int, dict] = {}
    for start, seq, stop, visit, day, rel, sched in con.execute(
        "SELECT start_s, stop_sequence, stop_id, visit, day, min(rel), min(sched_rel) FROM m "
        "WHERE line = ? AND direction_id = ? AND daytype = ? GROUP BY ALL ORDER BY ALL",
        [line, direction, kind],
    ).fetchall():
        index = stops.setdefault(stop, len(stops))
        pattern = found.setdefault(start, {"days": set(), "cells": {}, "sched": {}, "first": {}})
        pattern["days"].add(own[day])
        key = (index, visit)
        pattern["sched"][key] = min(sched, pattern["sched"].get(key, sched))
        pattern["first"][key] = min(seq, pattern["first"].get(key, seq))
        column = pattern["cells"].setdefault(key, {})
        column[own[day]] = min(rel, column.get(own[day], rel))
    packed = []
    for start, pattern in sorted(found.items()):
        order = sorted(pattern["days"])
        cells = sorted(
            pattern["cells"].items(),
            key=lambda item: (pattern["sched"][item[0]], pattern["first"][item[0]], item[0]),
        )
        grid = [[values.get(day) for day in order] for _, values in cells]
        scheduled = encode([[pattern["sched"][key]] for key, _ in cells])
        packed.append(
            [
                start,
                order,
                [index for (index, _), _ in cells],
                encode(grid),
                [row[0] for row in scheduled],
            ]
        )
    return {
        "line": line,
        "direction": direction,
        "day_type": kind,
        "days": days,
        "stops": list(stops),
        "patterns": packed,
    }


def batches(counts: list[tuple[str, int]]) -> list[list[str]]:
    """Lines grouped so each group holds about BATCH_ROWS rows."""
    groups: list[list[str]] = []
    total = 0
    for line, count in counts:
        if not groups or total + count > BATCH_ROWS:
            groups.append([])
            total = 0
        groups[-1].append(line)
        total += count
    return groups


def stop_list(catalogue: dict) -> list[list]:
    return [
        [stop_id, meta["name"], round(meta["lat"], 6), round(meta["lon"], 6)]
        for (agency, stop_id), meta in sorted(catalogue["stops"].items())
        if agency == BUS_AGENCY
    ]


def build(
    con: duckdb.DuckDBPyConnection,
    arrivals_dir: Path,
    last: str,
    types: dict[str, str],
    catalogue: dict,
    out: Path,
) -> tuple[list[str], list[tuple[str, int]], dict]:
    """Write the commute files under `out`/commute for the window ending `last`.

    `types` is the day type of each service date, and dates without one are left
    out. Lines are read in batches so the 56 days never sit in memory at once.
    Returns the names written, relative to `out`, the files over LIMIT gzipped
    with their sizes, and a summary of sizes. A line whose name cannot be a file
    name is left out and named in the summary's `skipped_lines`.
    """
    days = [day for day in window(last) if day in types]
    files = window_files(arrivals_dir, last)
    by_type = {kind: [day for day in days if types[day] == kind] for kind in DAY_TYPES}
    counts = con.execute(
        f"SELECT line, count(*) FROM read_parquet(?, hive_partitioning = false) "
        f"WHERE agency = '{BUS_AGENCY}' AND {DAY_SQL} IN (SELECT unnest(?)) AND {MEASURED} "
        "GROUP BY line ORDER BY line",
        [files, days],
    ).fetchall()

    names, entries, over, sizes = [], [], [], []
    skipped: set[str] = set()
    for group in batches(counts):
        load(con, files, {day: types[day] for day in days}, group)
        for line, direction, kind in con.execute(
            "SELECT DISTINCT line, direction_id, daytype FROM m ORDER BY ALL"
        ).fetchall():
            if not SAFE_NAME.fullmatch(line):
                if line not in skipped:
                    print(f"  commute: line {line!r} cannot be a file name, left out")
                skipped.add(line)
                continue
            payload = route_file(con, line, direction, kind, by_type[kind])
            name = f"commute/{line}-{direction}-{kind}.json"
            raw = write_json(out / name, payload)
            gzipped = len(gzip.compress((out / name).read_bytes(), 6))
            names.append(name)
            sizes.append((raw, gzipped))
            if gzipped > LIMIT:
                over.append((name, gzipped))
            entries.append(
                {
                    "line": line,
                    "direction": direction,
                    "day_type": kind,
                    "file": name,
                    "patterns": len(payload["patterns"]),
                    "days": len(by_type[kind]),
                }
            )
    con.execute("DROP TABLE IF EXISTS m")

    stops_raw = write_json(out / "commute" / "stops.json", stop_list(catalogue))
    write_json(
        out / "commute" / "index.json",
        {
            "first_day": days[0] if days else None,
            "last_day": days[-1] if days else None,
            "days": len(days),
            "unit": UNIT,
            "stops": "commute/stops.json",
            "files": entries,
        },
    )
    names += ["commute/stops.json", "commute/index.json"]
    summary = {
        "files": len(entries),
        "largest_gzip": max((g for _, g in sizes), default=0),
        "median_gzip": statistics.median(g for _, g in sizes) if sizes else 0,
        "total_raw": sum(r for r, _ in sizes) + stops_raw,
        "skipped_lines": sorted(skipped),
    }
    return sorted(names), sorted(over, key=lambda row: -row[1]), summary
