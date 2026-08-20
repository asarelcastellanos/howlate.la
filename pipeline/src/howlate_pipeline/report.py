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

import duckdb

# Measured on 2026-08-18 across all 120 lines. Ranges, not points, because real
# days differ: weekends run less service and holidays run almost none.
EXPECTED = {
    "join_rate":        (99.9, 100.0, "observations matching a scheduled stop"),
    "stop_id_match":    (99.9, 100.0, "reported stop_id agreeing with the timetable"),
    "coverage":         (55.0, 90.0,  "scheduled stops with a timed arrival"),
    "stopped_pct":      (35.0, 75.0,  "of those, timed from a STOPPED_AT record"),
    "median_delay_min": (-1.0, 6.0,   "median delay, mid-route"),
    "absurd_pct":       (0.0,  0.5,   "delays beyond an hour"),
    "early_pct":        (0.0,  2.0,   "mid-route arrivals over 5 min early"),
}


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

    keys = ["scheduled_stops", "measured", "stopped", "approached",
            "terminus_stopped", "terminus_approach", "trips", "lines",
            "median_delay", "p75", "p95", "p99", "absurd", "early", "with_delay"]
    stats = dict(zip(keys, row))

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
    stats |= dict(zip(["observations", "joined", "stop_match", "ambiguous"], obs))

    stats["join_rate"] = 100 * stats["joined"] / stats["observations"] if stats["observations"] else 0
    stats["stop_id_match"] = 100 * stats["stop_match"] / stats["joined"] if stats["joined"] else 0
    stats["coverage"] = 100 * stats["measured"] / stats["scheduled_stops"] if stats["scheduled_stops"] else 0
    stats["stopped_pct"] = 100 * stats["stopped"] / stats["scheduled_stops"] if stats["scheduled_stops"] else 0
    stats["median_delay_min"] = (stats["median_delay"] or 0) / 60
    stats["absurd_pct"] = 100 * stats["absurd"] / stats["with_delay"] if stats["with_delay"] else 0
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


def silent_lines(con: duckdb.DuckDBPyConnection) -> list[tuple]:
    """Lines the timetable ran today that nothing was ever seen on.

    No list of exceptions is needed. A line that does not run today has no
    scheduled stops and so cannot appear here, which is why the stadium shuttles
    are absent on an ordinary Tuesday without anyone having to say so.
    """
    return con.sql("""
        SELECT agency, line, count(*) AS scheduled_stops
        FROM arrivals GROUP BY agency, line
        HAVING count(*) FILTER (WHERE source <> 'none') = 0
        ORDER BY scheduled_stops DESC
    """).fetchall()


def show(con: duckdb.DuckDBPyConnection, service_date: str) -> bool:
    """Print the report. Returns True if everything was within expectations."""
    s = summarise(con)

    print(f"\n  {service_date}: {s['lines']} lines, {s['trips']:,} trips, "
          f"{s['scheduled_stops']:,} scheduled stops")
    print(f"  timed {s['measured']:,} ({s['coverage']:.1f}%): "
          f"{s['stopped']:,} from a stop record, "
          f"{s['approached']:,} recovered from the approach "
          f"(+{100 * s['approached'] / s['scheduled_stops']:.1f} points, of which "
          f"{s['terminus_approach']:,} are trip termini), "
          f"{s['scheduled_stops'] - s['measured']:,} never seen")
    print(f"  delay mid-route: median {s['median_delay'] / 60:+.1f} | p75 {s['p75'] / 60:+.1f} "
          f"| p95 {s['p95'] / 60:+.1f} | p99 {s['p99'] / 60:+.1f} min")

    print()
    for agency, lines, stops, measured in by_agency(con):
        print(f"  {agency:<12} {lines:>4} lines  {stops:>8,} scheduled  "
              f"{measured:>8,} measured ({100 * measured / stops:.1f}%)")

    print()
    ok = True
    for key, (low, high, label) in EXPECTED.items():
        value = s[key]
        good = low <= value <= high
        ok &= good
        print(f"  {'ok  ' if good else 'CHECK'} {value:8.2f}  {label} (expect {low} to {high})")

    # Two absolutes rather than ranges. Both were exactly zero across a full day
    # and neither can move without something real having changed.
    #
    # The terminus one is specifically about STOPPED_AT. Vehicles stop reporting a
    # trip before finishing it, so its last stop never produces one; the approach
    # records do reach it, which is how 9,071 terminus arrivals on 2026-08-18
    # became measurable for the first time. Narrowed rather than deleted, because
    # a STOPPED_AT appearing there would still mean the feed had changed.
    for count, label in ((s["terminus_stopped"], "STOPPED_AT records on a trip's final stop"),
                         (s["ambiguous"], "stop_sequence values reporting two different stop_ids")):
        good = count == 0
        ok &= good
        print(f"  {'ok  ' if good else 'CHECK'} {count:8,}  {label} (expect 0)")

    feeds = by_agency(con)
    good = len(feeds) == 2 and all(stops > 0 for _, _, stops, _ in feeds)
    ok &= good
    print(f"  {'ok  ' if good else 'CHECK'} {len(feeds):8,}  feeds contributing scheduled stops (expect 2)")

    silent = silent_lines(con)
    print(f"  {'ok  ' if not silent else 'CHECK'} {len(silent):8,}  lines scheduled today but never seen (expect 0)")
    for agency, line, stops in silent[:10]:
        print(f"          {agency} {line}: {stops:,} scheduled stops, nothing observed")

    return bool(ok and not silent)
