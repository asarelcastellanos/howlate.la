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

from howlate_pipeline import RAIL_AGENCY, __version__, railmatch
from howlate_pipeline.gtfs import line_code

# A stop a vehicle reported at, as opposed to one placed between two reports. The
# coverage numbers and the silent-lines check count only these, so a bug that
# stopped the feed reaching a line cannot be hidden by estimates around it.
SEEN = "source NOT IN ('none', 'interpolated')"

# Measured on 2026-08-18 across all 120 lines. Ranges, not points, because real
# days differ: weekends run less service and holidays run almost none.
EXPECTED = {
    # Counts an observation on a trip that every timetable copy lists only under
    # a service starting after the day as matched, so only a trip in no timetable,
    # or one under an expired or removed service, can fail it. The raw join_rate
    # stays in the stats. On 2026-11-14, 5,370 of the day's rail observations
    # (338 trips, all route 801) were on trips listed under six services that
    # start later, and 2026-11-07 had 214 on route 803. Every trip the vehicles
    # reported on 2026-10-31 and 2026-11-12 matched.
    "matched_rate": (
        99.9,
        100.0,
        "observations matching a scheduled stop, or a trip listed only under a later-start service",
    ),
    # The network-wide cap on matched_rate's exemption. If a calendar or
    # service-selection bug marked most of a day's services later-start, nearly
    # every observation would count as explained and matched_rate would pass.
    # Measured: 5,370 of 550,650 observations on 2026-11-14 (0.98%), 3,882 of
    # 636,571 on 2026-11-13 (0.61%), 1,083 of 534,060 on 2026-11-07 (0.20%), and
    # 0 on every other day checked. 5% leaves headroom and still fails a day
    # where most of the network is hidden. It does not see a part of the network
    # that is small against the whole, because rail is about 4% of observations
    # and one rail line less than that. explained_lines covers that.
    "explained_pct": (
        0.0,
        5.0,
        "observations on trips listed only under a later-start service",
    ),
    "stop_id_match": (99.9, 100.0, "reported stop_id agreeing with the timetable"),
    "coverage": (
        55.0,
        90.0,
        "scheduled stops with a timed arrival, not counting interpolated ones",
    ),
    "stopped_pct": (35.0, 75.0, "of those, timed from a STOPPED_AT record"),
    "median_delay_min": (-1.0, 6.0, "median delay, mid-route"),
    "absurd_pct": (0.0, 0.5, "delays beyond an hour"),
    "early_pct": (0.0, 2.0, "mid-route arrivals over 5 min early"),
    # Added with v2 and checked on 18 to 20 August: every timed arrival named a
    # vehicle, and 98.2% to 98.4% of scheduled trips were seen. The trips range
    # stays wide until weekends and holidays have been measured.
    "vehicle_known": (99.9, 100.0, "timed arrivals naming a vehicle"),
    "trips_seen": (90.0, 100.0, "scheduled trips with any report"),
    # The highest share, on any one rail line with MIN_LINE_RUNS or more judged
    # runs, of runs that fit another trip of the line much better than the trip
    # they reported (see rail_misfits). Per line because a network-wide share
    # dilutes: on 2026-11-13 route 801 had 21.5% (71 of 331 runs) and all rail
    # 5.3%. Measured on 48 of the archive's 91 days, so a half-archive sample:
    # 2026-08-18 to 09-18 (09-19 failed to load), 09-20 to 09-27, 10-24, 10-25,
    # 10-31, 11-07, 11-10, 11-13, 11-14 and 11-15. The highest line was a median
    # 2.6%. 42 days stayed at or under 9.0%, and 6 were over 10%: 2026-08-22 (14.5%
    # on route 805), 09-15 (10.8%, 805), 09-18 (11.2%, 805), 11-13 (21.5%, 801),
    # 11-14 (24.4%, 801) and 11-15 (18.3%, 801). The three highest of the 42 were
    # 7.9% (08-26), 8.2% (09-20) and 9.0% (09-13). On 09-13 the 8 misfit runs on route
    # 802 reported a trip 20 to 60 minutes off, so those days are not clean, and 10
    # is where the measured days stop being close to each other. The A line (801)
    # was over the limit on 3 of the 4 days of #177 and not on 2026-11-07, where
    # its mismatches are later-start ids with no timetable to fit, which
    # explained_pct counts. Those days read the raw files only to 07:59 UTC the
    # next day, which leaves out the end of the service day after local midnight on
    # the days after 1 November. The full pipeline on 2026-11-13 found 70 misfits in
    # 342 runs on route 801 (20.5%) against 71 in 331 here, so the shares near the
    # limit can differ by about a point.
    "rail_misfit_pct": (
        0.0,
        10.0,
        "rail runs that fit another trip's timetable much better than their reported trip, "
        "on the worst line",
    ),
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


def summarise(
    con: duckdb.DuckDBPyConnection, rail: list[tuple[str, int, int]] | None = None
) -> dict[str, float]:
    """Every headline number for the day, in one pass over the joined table."""
    row = con.sql(f"""
        SELECT
          count(*)                                                  AS scheduled_stops,
          count(*) FILTER (WHERE {SEEN})                            AS measured,
          count(*) FILTER (WHERE source = 'interpolated')           AS interpolated,
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
        "interpolated",
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

    explained = explained_unmatched(con)
    stats["explained"] = sum(observations for _, observations, _ in explained)
    stats["explained_trips"] = sum(trips for _, _, trips in explained)

    stats["join_rate"] = (
        100 * stats["joined"] / stats["observations"] if stats["observations"] else 0
    )
    stats["matched_rate"] = (
        100 * (stats["joined"] + stats["explained"]) / stats["observations"]
        if stats["observations"]
        else 0
    )
    stats["explained_pct"] = (
        100 * stats["explained"] / stats["observations"] if stats["observations"] else 0
    )
    stats["stop_id_match"] = 100 * stats["stop_match"] / stats["joined"] if stats["joined"] else 0
    stats["coverage"] = (
        100 * stats["measured"] / stats["scheduled_stops"] if stats["scheduled_stops"] else 0
    )
    stats["interpolated_pct"] = pct(stats["interpolated"], stats["scheduled_stops"])
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
    if rail is None:
        rail = rail_misfits(con)
    stats["rail_misfit_pct"] = max(
        (pct(misfits, runs) for _, runs, misfits in rail if runs >= MIN_LINE_RUNS), default=0.0
    )
    return stats


ADVISORY_NOTE = "advisory while the rail matcher is off, so a failure here does not fail the day"

EXPLAINED_NOTE = (
    "These trips are in every timetable copy that lists them only under a service whose "
    "start date is after this date, so they have no scheduled stops to grade against "
    "and stay ungraded."
)

# One row per trip: its route, and whether it is explained. A trip any copy
# lists under a running service is a real join failure, so it is not explained
# however another copy lists it. An expired service, a wrong weekday, a
# calendar_dates removal and a service with no calendar row are not explained
# either, because only a later start date has been measured as a cause.
_TRIP_LISTING = """
    SELECT agency, trip_id, min(route_id) AS route_id,
           NOT bool_or(service_active) AND bool_and(service_later) AS explained
    FROM listed_trips GROUP BY agency, trip_id
"""


def explained_unmatched(con: duckdb.DuckDBPyConnection) -> list[tuple]:
    """Observations on trips that no copy lists under a running service, only later-start.

    Per feed: observations, and distinct trips. Every listing of the trip is
    in trips.txt under a service whose start_date is after today, so it has no
    row in `scheduled` and the observation cannot join. A trip in no copy read
    is not counted here, and neither is a stop the timetable lacks on a trip
    that does run today, or a trip under an expired or removed service.
    """
    return con.sql(f"""
        SELECT o.agency, count(*) AS observations, count(DISTINCT o.trip_id) AS trips
        FROM observed o
        JOIN ({_TRIP_LISTING}) l
          ON l.agency = o.agency AND l.trip_id = o.trip_id AND l.explained
        GROUP BY o.agency ORDER BY o.agency
    """).fetchall()


# Fewest observed trips on a line before it can fail explained_lines. Without a
# floor, a line with one stray report on a later-start trip would fail the day.
# The 5 is a judgment, not a measurement: the explained trips on 2026-11-14 were
# 338 of 1,336 rail trips (route 801 also had 233 that matched), on 2026-11-13
# 244 of 1,647, and on 2026-11-07 214 of 1,110. Each of those lines had matched
# trips beside its explained ones, which is what keeps the check passing.
MIN_LINE_TRIPS = 5


def fully_explained_lines(con: duckdb.DuckDBPyConnection) -> list[tuple]:
    """Lines with at least MIN_LINE_TRIPS observed trips, every one of them explained.

    A line is hidden when nothing the vehicles reported on it was graded, and
    neither explained_pct nor matched_rate can see that for a small line. The
    line is the trip's route_id through `gtfs.line_code`, counted per feed. A
    trip in no timetable copy has no route here and is left to matched_rate.
    """
    by_route = con.sql(f"""
        SELECT l.agency, l.route_id, count(*) AS trips,
               count(*) FILTER (WHERE l.explained) AS explained
        FROM (SELECT DISTINCT agency, trip_id FROM observed) o
        JOIN ({_TRIP_LISTING}) l ON l.agency = o.agency AND l.trip_id = o.trip_id
        GROUP BY l.agency, l.route_id
    """).fetchall()
    totals: dict[tuple[str, str], list[int]] = {}
    for agency, route_id, trips, explained in by_route:
        counts = totals.setdefault((agency, line_code(route_id)), [0, 0])
        counts[0] += trips
        counts[1] += explained
    return sorted(
        (agency, line, trips)
        for (agency, line), (trips, explained) in totals.items()
        if trips >= MIN_LINE_TRIPS and trips == explained
    )


# Fewest non-origin stops a rail run must be timed at before it is judged. With 3
# the share on 2026-11-07 was 2.3% for all rail, with 5 it was 1.1% and with 8
# 0.8%, so a short run is mostly noise. The same days' other shares moved by under
# a point between 5 and 8.
MIN_RUN_STOPS = 5

# How close, in seconds, another trip must fit, and how much worse the reported
# trip must fit than it. At 60 the highest line was a median 2.6% over the 48
# measured days. At 120 it was a median 7.9% and 14 days were over 10%, because a
# train a few minutes late is within 120 s of the trip behind it. The margin
# barely matters: 180 instead of 300 changed the highest line on 3 days, by 0.4 to
# 3.0 points, and moved no day across the 10% limit. 300 is under the 8 minute
# headway of the K line.
FIT_SECONDS = 60
FIT_MARGIN = 300

# Fewest judged runs on a line before it can fail the check. Lines had 60 to 459
# judged runs a day on the measured days, apart from 2026-08-21, when the archive
# held 190 of the day's 382 files and each line had 24 to 52. Below 30, one run
# is over 3%.
MIN_LINE_RUNS = 30


def rail_misfits(con: duckdb.DuckDBPyConnection) -> list[tuple[str, int, int]]:
    """For each rail line, the runs judged and how many fit another trip much better.

    A run is one vehicle on one trip_id of `observations`, which is the trip the
    grader used. With the matcher on, a run `arrivals.match_rail_runs` moved to
    its fitted trip is judged on that trip and a run it dropped is not judged, so
    a day when the feed labels trains with the wrong ids fails only for the runs
    the matcher trusted. Its miss against a trip is the
    median, over the stops it was timed at, of the seconds between its first
    STOPPED_AT and the trip's scheduled arrival. The run is a misfit when another
    trip on the same route and direction, scheduled at every stop the run was timed
    at, has a miss of at most FIT_SECONDS and the reported trip's miss is at least
    FIT_MARGIN worse. Only runs timed at MIN_RUN_STOPS or more non-origin stops are
    judged, and a run on a trip with no scheduled stops cannot be, so a later-start
    trip is left to explained_pct. The line is the judged trip's route_id.

    A failing `rail_misfit_pct` is advisory while `railmatch.ENABLED` is False
    (see `binding`): it shows as failed here and in the saved report but does not
    fail the day.
    """
    return con.execute(
        """
        WITH timed AS (
            SELECT o.vehicle_id, o.trip_id, s.stop_id, s.route_id, s.direction_id,
                   min(o.ts) AS ts
            FROM observations o
            JOIN scheduled s
              ON s.agency = o.agency AND s.trip_id = o.trip_id
             AND s.stop_sequence = o.stop_sequence
            WHERE o.agency = ? AND o.status = 'STOPPED_AT'
              AND o.vehicle_id IS NOT NULL AND NOT s.is_origin
            GROUP BY ALL
        ),
        runs AS (
            SELECT vehicle_id, trip_id, count(*) AS stops
            FROM timed GROUP BY ALL HAVING count(*) >= ?
        ),
        fits AS (
            SELECT t.vehicle_id, t.trip_id, t.route_id, c.trip_id AS fitted,
                   median(abs(t.ts - c.scheduled_arrival)) AS miss
            FROM timed t
            JOIN runs r USING (vehicle_id, trip_id)
            JOIN scheduled c
              ON c.agency = ? AND c.route_id = t.route_id AND c.direction_id = t.direction_id
             AND c.stop_id = t.stop_id AND NOT c.is_origin
            GROUP BY t.vehicle_id, t.trip_id, t.route_id, c.trip_id, r.stops
            HAVING count(*) = r.stops
        ),
        judged AS (
            SELECT route_id,
                   min(miss) FILTER (WHERE fitted = trip_id) AS reported,
                   min(miss) FILTER (WHERE fitted <> trip_id) AS other
            FROM fits GROUP BY vehicle_id, trip_id, route_id
        )
        SELECT route_id, count(*),
               count(*) FILTER (WHERE other <= ? AND reported - other >= ?)
        FROM judged GROUP BY route_id ORDER BY route_id
        """,
        [RAIL_AGENCY, MIN_RUN_STOPS, RAIL_AGENCY, FIT_SECONDS, FIT_MARGIN],
    ).fetchall()


def rail_matching(con: duckdb.DuckDBPyConnection) -> list[tuple[str, int, int, int]]:
    """For each rail line, the runs trusted, matched by position, and left ungraded.

    Empty when the matcher is off or the day had no rail runs.
    """
    return con.sql("""
        SELECT line, count(*) FILTER (WHERE outcome = 'trusted'),
               count(*) FILTER (WHERE outcome = 'matched'),
               count(*) FILTER (WHERE outcome = 'ungraded')
        FROM rail_runs GROUP BY line ORDER BY line
    """).fetchall()


def notes(stats: dict) -> list[str]:
    """One plain sentence for each thing on this day that explains a number."""
    return [EXPLAINED_NOTE] if stats["explained"] else []


def by_agency(con: duckdb.DuckDBPyConnection) -> list[tuple]:
    """Scheduled stops and lines per feed.

    Worth its own check because a whole feed can disappear without any other
    number looking wrong. Choosing the wrong rail timetable once deleted all six
    rail lines while coverage, delay and stop_id agreement all stayed green, and
    only the join rate dipped, which reads like a data problem rather than a
    missing feed.
    """
    return con.sql(f"""
        SELECT agency, count(DISTINCT line) AS lines, count(*) AS scheduled_stops,
               count(*) FILTER (WHERE {SEEN}) AS measured,
               count(*) FILTER (WHERE source = 'interpolated') AS interpolated
        FROM arrivals GROUP BY agency ORDER BY agency
    """).fetchall()


def _never_seen(con: duckdb.DuckDBPyConnection) -> list[tuple]:
    return con.sql(f"""
        SELECT agency, line, count(*) AS scheduled_stops
        FROM arrivals GROUP BY agency, line
        HAVING count(*) FILTER (WHERE {SEEN}) = 0
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
    rail = rail_misfits(con)
    s = summarise(con, rail)

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
        f"  of those never seen, {s['interpolated']:,} bus stops were placed between two "
        f"reports ({s['interpolated_pct']:.1f}% of scheduled stops), so "
        f"{s['measured'] + s['interpolated']:,} have a delay "
        f"({pct(s['measured'] + s['interpolated'], s['scheduled_stops']):.1f}%)"
    )
    print(
        f"  delay mid-route: median {minutes(s['median_delay'])} | p75 {minutes(s['p75'])} "
        f"| p95 {minutes(s['p95'])} | p99 {minutes(s['p99'])} min"
    )

    print()
    for agency, lines, stops, measured, interpolated in by_agency(con):
        print(
            f"  {agency:<12} {lines:>4} lines  {stops:>8,} scheduled  "
            f"{measured:>8,} measured ({pct(measured, stops):.1f}%)  "
            f"{interpolated:>8,} interpolated ({pct(interpolated, stops):.1f}%)"
        )

    if s["explained"]:
        print()
        print(
            "  explained: "
            + ", ".join(
                f"{agency} {observations:,} observations on {trips:,} trips"
                for agency, observations, trips in explained_unmatched(con)
            )
        )
        for note in notes(s):
            print(f"  {note}")

    print()
    found = checks(con, s)
    for check in found:
        mark = "ok  " if check["ok"] else "CHECK"
        if check["kind"] == "range":
            print(
                f"  {mark} {check['value']:8.2f}  {check['label']} "
                f"(expect {check['low']} to {check['high']})"
            )
        else:
            print(f"  {mark} {check['value']:8,}  {check['label']} (expect {check['expect']})")
        if not binding(check):
            print(f"          {ADVISORY_NOTE}")
    for agency, line, stops in silent_lines(con)[:10]:
        print(f"          {agency} {line}: {stops:,} scheduled stops, nothing observed")
    for agency, line, stops in silent_event_lines(con):
        print(
            f"          info {agency} {line}: event-only line, {stops:,} scheduled stops, "
            "nothing observed, not checked"
        )
    for line, trusted, matched, ungraded in rail_matching(con):
        print(
            f"          {RAIL_AGENCY} {line}: {trusted:,} runs graded on their reported trip, "
            f"{matched:,} matched by position, {ungraded:,} left ungraded"
        )
    limit = EXPECTED["rail_misfit_pct"][1]
    for line, runs, misfits in rail:
        if runs >= MIN_LINE_RUNS and pct(misfits, runs) > limit:
            print(
                f"          {RAIL_AGENCY} {line}: {misfits:,} of {runs:,} runs fit another trip better"
            )
    return day_ok(found)


def binding(check: dict) -> bool:
    """Whether a failure of this check fails the day.

    `rail_misfit_pct` judges the trip ids the feed reported while the rail matcher
    is off. On a split-service day such as 2026-11-13 it reads 20.5% on route 801
    against the 10% limit, and nothing in the pipeline can fix that cause. It is
    reported and saved but does not fail the day. Turning the matcher on makes it
    binding again.
    """
    return railmatch.ENABLED or check["name"] != "rail_misfit_pct"


def day_ok(found: list[dict]) -> bool:
    """Whether every binding check passed."""
    return all(check["ok"] for check in found if binding(check))


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
    # trip before finishing it, so its last stop has produced none on the days
    # checked; the approach records do reach it, which is how 9,071 terminus
    # arrivals on 2026-08-18 became measurable for the first time. Narrowed
    # rather than deleted, because a STOPPED_AT appearing there would still mean
    # the feed had changed.
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
            "ok": len(feeds) == 2 and all(stops > 0 for _, _, stops, _, _ in feeds),
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

    hidden = fully_explained_lines(con)
    found.append(
        {
            "name": "explained_lines",
            "kind": "count",
            "label": "lines whose observed trips are all explained",
            "value": len(hidden),
            "expect": 0,
            "ok": not hidden,
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
    rail = rail_misfits(con)
    s = summarise(con, rail)
    found = checks(con, s)
    return {
        "service_date": f"{service_date[:4]}-{service_date[4:6]}-{service_date[6:]}",
        "pipeline_version": __version__,
        "stats": s,
        "agencies": [
            {
                "agency": agency,
                "lines": lines,
                "scheduled_stops": stops,
                "measured": measured,
                "interpolated": interpolated,
            }
            for agency, lines, stops, measured, interpolated in by_agency(con)
        ],
        "silent_lines": [
            {"agency": agency, "line": line, "scheduled_stops": stops}
            for agency, line, stops in silent_lines(con)
        ],
        "silent_event_lines": [
            {"agency": agency, "line": line, "scheduled_stops": stops}
            for agency, line, stops in silent_event_lines(con)
        ],
        "rail_misfits": [
            {"line": line, "runs": runs, "misfits": misfits} for line, runs, misfits in rail
        ],
        "rail_matching": [
            {"line": line, "trusted": trusted, "matched": matched, "ungraded": ungraded}
            for line, trusted, matched, ungraded in rail_matching(con)
        ],
        "explained_unmatched": [
            {"agency": agency, "observations": observations, "trips": trips}
            for agency, observations, trips in explained_unmatched(con)
        ],
        "notes": notes(s),
        "checks": found,
        "ok": day_ok(found),
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
