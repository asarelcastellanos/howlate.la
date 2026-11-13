"""The checks that run every time, and the numbers they are checked against.

These are the point of the job, not decoration. Every figure below was measured
across the whole network on service day 2026-08-18, so a later day that drifts
away from them is saying something changed: Metro's feed, the timetable, or this
code. Without them a broken join still produces a plausible-looking median and
nothing anywhere says otherwise.

A check that fails is printed and the run carries on. The output is still worth
having, and a job that refuses to write anything because one line looks odd
would lose a day of results to protect nothing.
"""

import json
from pathlib import Path

import duckdb

from howlate_pipeline import __version__

# Measured on 2026-08-18 across all 120 lines. Ranges, not points, because real
# days differ: weekends run less service and holidays run almost none.
EXPECTED = {
    "join_rate": (99.9, 100.0, "observations matching a scheduled stop"),
    "stop_id_match": (99.9, 100.0, "reported stop_id agreeing with the timetable"),
    "coverage": (55.0, 90.0, "scheduled stops with a timed arrival"),
    "stopped_pct": (35.0, 75.0, "of those, timed from a STOPPED_AT record"),
    "median_delay_min": (-1.0, 6.0, "median delay, mid-route"),
    "absurd_pct": (0.0, 0.5, "delays beyond an hour"),
    "early_pct": (0.0, 2.0, "mid-route arrivals over 5 min early"),
    # Added with v2 and checked on 18 to 20 August: every timed arrival named a
    # vehicle, and 98.2% to 98.4% of scheduled trips were seen. The trips range
    # stays wide until weekends and holidays have been measured.
    "vehicle_known": (99.9, 100.0, "timed arrivals naming a vehicle"),
    "trips_seen": (90.0, 100.0, "scheduled trips with any report"),
}


# Stadium shuttles that the bus timetable schedules on some days and the vehicle
# feed never reports. A subset of EVENT_ONLY in
# collector/src/howlate_collector/routes.py (9, 22 and 694 to 697), copied here
# because the two packages install separately and neither may import the other.
# A test reads the collector's file and fails if this set holds a line that the
# collector's does not.
#
# Only the lines that are silent on every day they are scheduled are exempt.
# Over the 85 graded days 2026-08-18 to 2026-11-10, lines 9 and 22 were
# scheduled on the same 24 days and had no timed stop on any of them. Line 9 had
# 38 trips and 76 scheduled stops a day, line 22 had 19 trips and 114. That
# failed the silent-lines check on all 24. Whether Metro ran them on those days
# is not established.
#
# Lines 694 to 697 stay under the check. Line 697 was scheduled on 6 days with
# 50 trips a day, and between 29 and 40 of those trips had a timed arrival each
# day, so a silent 697 would be an outage that exempting it would hide. Lines
# 694 to 696 were not scheduled on any of the 85 days.
EVENT_ONLY = frozenset({"9", "22"})


def summarise(con: duckdb.DuckDBPyConnection) -> dict[str, float]:
    """Every headline number for the day, in one pass over the joined table."""
    row = con.sql("""
        SELECT
          count(*)                                                  AS scheduled_stops,
          count(*) FILTER (WHERE source <> 'none')                  AS measured,
          count(*) FILTER (WHERE source = 'stopped_at')            AS stopped,
          count(*) FILTER (WHERE source = 'approach')              AS approached,
          count(*) FILTER (WHERE is_terminus AND source = 'stopped_at') AS terminus_stopped,
          count(*) FILTER (WHERE is_terminus AND source = 'approach')   AS terminus_approach,
          count(DISTINCT trip_id)                                   AS trips,
          count(DISTINCT line)                                      AS lines,
          median(delay_seconds) FILTER (WHERE NOT is_origin)        AS median_delay,
          quantile_cont(delay_seconds, 0.75) FILTER (WHERE NOT is_origin) AS p75,
          quantile_cont(delay_seconds, 0.95) FILTER (WHERE NOT is_origin) AS p95,
          quantile_cont(delay_seconds, 0.99) FILTER (WHERE NOT is_origin) AS p99,
          count(*) FILTER (WHERE abs(delay_seconds) > 3600)         AS absurd,
          count(*) FILTER (WHERE NOT is_origin AND delay_seconds < -300) AS early,
          count(*) FILTER (WHERE delay_seconds IS NOT NULL)         AS with_delay
        FROM arrivals
    """).fetchone()

    keys = [
        "scheduled_stops",
        "measured",
        "stopped",
        "approached",
        "terminus_stopped",
        "terminus_approach",
        "trips",
        "lines",
        "median_delay",
        "p75",
        "p95",
        "p99",
        "absurd",
        "early",
        "with_delay",
    ]
    stats = dict(zip(keys, row, strict=True))

    # Observations are counted from the observation side, not the joined side: a
    # report that only ever looked at rows that joined could never notice one
    # that did not.
    obs = con.sql("""
        SELECT count(*) AS total,
               count(*) FILTER (WHERE s.trip_id IS NOT NULL) AS joined,
               count(*) FILTER (WHERE s.stop_id = o.reported_stop_id) AS stop_match,
               count(*) FILTER (WHERE o.distinct_stop_ids > 1) AS ambiguous
        FROM observed o
        LEFT JOIN scheduled s
          ON s.agency = o.agency AND s.trip_id = o.trip_id
         AND s.stop_sequence = o.stop_sequence
    """).fetchone()
    stats |= dict(zip(["observations", "joined", "stop_match", "ambiguous"], obs, strict=True))

    stats["join_rate"] = (
        100 * stats["joined"] / stats["observations"] if stats["observations"] else 0
    )
    stats["stop_id_match"] = 100 * stats["stop_match"] / stats["joined"] if stats["joined"] else 0
    stats["coverage"] = (
        100 * stats["measured"] / stats["scheduled_stops"] if stats["scheduled_stops"] else 0
    )
    stats["stopped_pct"] = (
        100 * stats["stopped"] / stats["scheduled_stops"] if stats["scheduled_stops"] else 0
    )
    stats["median_delay_min"] = (stats["median_delay"] or 0) / 60
    stats["absurd_pct"] = 100 * stats["absurd"] / stats["with_delay"] if stats["with_delay"] else 0
    stats |= dict(
        zip(
            ["timed", "timed_with_vehicle"],
            con.sql("""
                SELECT count(*) FILTER (WHERE actual_time IS NOT NULL),
                       count(*) FILTER (WHERE actual_time IS NOT NULL AND vehicle_id IS NOT NULL)
                FROM arrivals
            """).fetchall()[0],
            strict=True,
        )
    )
    stats["vehicle_known"] = (
        100 * stats["timed_with_vehicle"] / stats["timed"] if stats["timed"] else 0
    )
    trips_total, trips_seen = con.sql(
        "SELECT count(*), count(*) FILTER (WHERE reports > 0) FROM trips"
    ).fetchall()[0]
    stats["trips_seen"] = 100 * trips_seen / trips_total if trips_total else 0
    stats["early_pct"] = 100 * stats["early"] / stats["with_delay"] if stats["with_delay"] else 0
    return stats


def by_agency(con: duckdb.DuckDBPyConnection) -> list[tuple]:
    """Scheduled stops and lines per feed.

    Worth its own check because a whole feed can disappear without any other
    number looking wrong. Choosing the wrong rail timetable once deleted all six
    rail lines while coverage, delay and stop_id agreement all stayed green, and
    only the join rate dipped, which reads like a data problem rather than a
    missing feed.
    """
    return con.sql("""
        SELECT agency, count(DISTINCT line) AS lines, count(*) AS scheduled_stops,
               count(*) FILTER (WHERE source <> 'none') AS measured
        FROM arrivals GROUP BY agency ORDER BY agency
    """).fetchall()


def _never_seen(con: duckdb.DuckDBPyConnection) -> list[tuple]:
    return con.sql("""
        SELECT agency, line, count(*) AS scheduled_stops
        FROM arrivals GROUP BY agency, line
        HAVING count(*) FILTER (WHERE source <> 'none') = 0
        -- Ties broken by name, so the saved report is the same on every run.
        ORDER BY scheduled_stops DESC, agency, line
    """).fetchall()


def silent_lines(con: duckdb.DuckDBPyConnection) -> list[tuple]:
    """Lines the timetable ran today that nothing was ever seen on.

    A line that does not run today has no scheduled stops and so cannot appear
    here. Lines 9 and 22 are the exception: the timetable schedules them on
    days the feed never reports them, so they are left out and listed by
    silent_event_lines instead. Every other silent line, including the other
    shuttles, is a fault.
    """
    return [row for row in _never_seen(con) if row[1] not in EVENT_ONLY]


def silent_event_lines(con: duckdb.DuckDBPyConnection) -> list[tuple]:
    """Exempt event-only lines (9 and 22) that were scheduled today and never seen.

    Informational only. Nothing was measured on these, and a day where they
    were never seen does not say whether Metro ran them.
    """
    return [row for row in _never_seen(con) if row[1] in EVENT_ONLY]


def pct(part: float, whole: float) -> float:
    return 100 * part / whole if whole else 0.0


def minutes(seconds: float | None) -> str:
    """A delay in minutes, or n/a for a day with nothing timed mid-route."""
    return "n/a" if seconds is None else f"{seconds / 60:+.1f}"


def show(con: duckdb.DuckDBPyConnection, service_date: str) -> bool:
    """Print the report. Returns True if everything was within expectations."""
    s = summarise(con)

    print(
        f"\n  {service_date}: {s['lines']} lines, {s['trips']:,} trips, "
        f"{s['scheduled_stops']:,} scheduled stops"
    )
    print(
        f"  timed {s['measured']:,} ({s['coverage']:.1f}%): "
        f"{s['stopped']:,} from a stop record, "
        f"{s['approached']:,} recovered from the approach "
        f"(+{pct(s['approached'], s['scheduled_stops']):.1f} points, of which "
        f"{s['terminus_approach']:,} are trip termini), "
        f"{s['scheduled_stops'] - s['measured']:,} never seen"
    )
    print(
        f"  delay mid-route: median {minutes(s['median_delay'])} | p75 {minutes(s['p75'])} "
        f"| p95 {minutes(s['p95'])} | p99 {minutes(s['p99'])} min"
    )

    print()
    for agency, lines, stops, measured in by_agency(con):
        print(
            f"  {agency:<12} {lines:>4} lines  {stops:>8,} scheduled  "
            f"{measured:>8,} measured ({pct(measured, stops):.1f}%)"
        )

    print()
    ok = True
    for check in checks(con, s):
        ok &= check["ok"]
        mark = "ok  " if check["ok"] else "CHECK"
        if check["kind"] == "range":
            print(
                f"  {mark} {check['value']:8.2f}  {check['label']} "
                f"(expect {check['low']} to {check['high']})"
            )
        else:
            print(f"  {mark} {check['value']:8,}  {check['label']} (expect {check['expect']})")
    for agency, line, stops in silent_lines(con)[:10]:
        print(f"          {agency} {line}: {stops:,} scheduled stops, nothing observed")
    for agency, line, stops in silent_event_lines(con):
        print(
            f"          info {agency} {line}: event-only line, {stops:,} scheduled stops, "
            "nothing observed, not checked"
        )
    return ok


def checks(con: duckdb.DuckDBPyConnection, s: dict) -> list[dict]:
    """Every check, with its value and whether it passed.

    One list feeds both the printed report and the saved one, so the two
    cannot disagree about what passed.
    """
    found = [
        {
            "name": key,
            "kind": "range",
            "label": label,
            "value": s[key],
            "low": low,
            "high": high,
            "ok": low <= s[key] <= high,
        }
        for key, (low, high, label) in EXPECTED.items()
    ]

    # Two absolutes rather than ranges. Both were exactly zero across a full day
    # and neither can move without something real having changed.
    #
    # The terminus one is specifically about STOPPED_AT. Vehicles stop reporting a
    # trip before finishing it, so its last stop never produces one; the approach
    # records do reach it, which is how 9,071 terminus arrivals on 2026-08-18
    # became measurable for the first time. Narrowed rather than deleted, because
    # a STOPPED_AT appearing there would still mean the feed had changed.
    for name, label in (
        ("terminus_stopped", "STOPPED_AT records on a trip's final stop"),
        ("ambiguous", "stop_sequence values reporting two different stop_ids"),
    ):
        found.append(
            {"name": name, "kind": "count", "label": label, "value": s[name], "expect": 0,
             "ok": s[name] == 0}
        )  # fmt: skip

    feeds = by_agency(con)
    found.append(
        {
            "name": "feeds",
            "kind": "count",
            "label": "feeds contributing scheduled stops",
            "value": len(feeds),
            "expect": 2,
            "ok": len(feeds) == 2 and all(stops > 0 for _, _, stops, _ in feeds),
        }
    )

    silent = silent_lines(con)
    found.append(
        {
            "name": "silent_lines",
            "kind": "count",
            "label": "lines scheduled today but never seen",
            "value": len(silent),
            "expect": 0,
            "ok": not silent,
        }
    )
    return found


def document(con: duckdb.DuckDBPyConnection, service_date: str) -> dict:
    """The whole report as data, for saving beside the day's Parquet.

    The site's behind-the-scenes page will read these, and the backfill treats a
    saved report as the sign that a day finished, because it is written last.
    No wall-clock time goes in, so regrading an unchanged day writes the same
    bytes.
    """
    s = summarise(con)
    found = checks(con, s)
    return {
        "service_date": f"{service_date[:4]}-{service_date[4:6]}-{service_date[6:]}",
        "pipeline_version": __version__,
        "stats": s,
        "agencies": [
            {"agency": agency, "lines": lines, "scheduled_stops": stops, "measured": measured}
            for agency, lines, stops, measured in by_agency(con)
        ],
        "silent_lines": [
            {"agency": agency, "line": line, "scheduled_stops": stops}
            for agency, line, stops in silent_lines(con)
        ],
        "silent_event_lines": [
            {"agency": agency, "line": line, "scheduled_stops": stops}
            for agency, line, stops in silent_event_lines(con)
        ],
        "checks": found,
        "ok": all(check["ok"] for check in found),
    }


def save(document: dict, path: Path) -> Path:
    """Write one report as sorted, compact JSON.

    Written beside the target and renamed, because a report on disk is what
    marks a day done when nothing is uploaded, and a half-written one must not.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".partial")
    partial.write_text(json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n")
    partial.replace(path)
    return path
