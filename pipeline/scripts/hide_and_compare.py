"""Check `arrivals.interpolate` against stops whose real time is known.

Takes every bus stop that has a STOPPED_AT report, hides it, times it again
from the reports around it, and compares the two. The estimate for a stop uses
only reports at lower and higher stop indexes, never the ones at the stop
itself, so hiding every such stop at once gives each one the estimate it would
get if only it were hidden. Rows that were already skipped are estimated too and
left out of the comparison.

    python3 pipeline/scripts/hide_and_compare.py grade --raw-dir RAW --out OUT DAY...
    python3 pipeline/scripts/hide_and_compare.py summarise OUT

`grade` reads the raw files and the timetable from RAW and the cache and writes
OUT/hide_and_compare_DAY.parquet. It never uploads. `summarise` prints the
errors by the gap between the two surrounding reports, which is what the 300 s
limit in `arrivals.MAX_GAP` was chosen from.
"""

import argparse
import sys
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from howlate_pipeline import BUS_AGENCY, arrivals, gtfs  # noqa: E402
from howlate_pipeline.__main__ import Bucket  # noqa: E402
from howlate_pipeline.aggregate import ONTIME_FROM, ONTIME_TO  # noqa: E402

# Each stop is filed under the first of these that estimates it, so its bucket
# is the smallest limit on the gap that would still have placed it. The last is
# larger than any gap in a day.
LIMITS = (60, 120, 180, 240, 300, 450, 600, 10**9)
LABELS = {
    60: "1 under 60 s",
    120: "2 60 to 120 s",
    180: "3 120 to 180 s",
    240: "4 180 to 240 s",
    300: "5 240 to 300 s",
    450: "6 300 to 450 s",
    600: "7 450 to 600 s",
    10**9: "8 over 600 s",
}


def grade(service_date: str, raw_dir: Path, cache: Path, out: Path) -> None:
    con = arrivals.connect()
    files = arrivals.local_files(raw_dir, service_date)
    arrivals.load_observations(con, files, service_date)
    directories = gtfs.prepare(
        Bucket()(), service_date, cache / "gtfs", arrivals.observed_trip_ids(con), {}
    )
    arrivals.load_schedule(con, directories, service_date, {})
    arrivals.match(con, service_date)

    # Dwell is how long the bus said it was stopped. A short one is the closest
    # a stop with a real report comes to a stop the bus rolled past.
    con.execute(
        """
        CREATE TABLE truth AS
        SELECT trip_id, stop_sequence, epoch(scheduled_time) AS scheduled,
               epoch(actual_time) AS actual,
               epoch(departure_time) - epoch(actual_time) AS dwell
        FROM arrivals WHERE agency = ? AND source = 'stopped_at' AND NOT is_origin
    """,
        [BUS_AGENCY],
    )
    con.execute("CREATE TABLE base AS SELECT * FROM arrivals")
    con.execute(
        """
        UPDATE base SET source = 'none', actual_time = NULL, delay_seconds = NULL
        WHERE agency = ? AND source = 'stopped_at' AND NOT is_origin
    """,
        [BUS_AGENCY],
    )

    con.execute(
        "CREATE TABLE result (trip_id VARCHAR, stop_sequence INTEGER, limit_s BIGINT, est DOUBLE)"
    )
    for limit in LIMITS:
        con.execute("CREATE OR REPLACE TABLE arrivals AS SELECT * FROM base")
        arrivals.interpolate(con, limit)
        con.execute(
            """
            INSERT INTO result
            SELECT a.trip_id, a.stop_sequence, ?, epoch(a.actual_time)
            FROM arrivals a JOIN truth t USING (trip_id, stop_sequence)
            WHERE a.source = 'interpolated'
        """,
            [limit],
        )
    out.mkdir(parents=True, exist_ok=True)
    con.execute(
        f"""
        COPY (
            SELECT t.trip_id, t.stop_sequence, t.scheduled, t.actual, t.dwell,
                   min(r.limit_s) AS limit_s,
                   arg_min(r.est, r.limit_s) AS est
            FROM truth t LEFT JOIN result r USING (trip_id, stop_sequence)
            GROUP BY ALL
        ) TO '{out / f"hide_and_compare_{service_date}.parquet"}' (FORMAT parquet)
    """
    )
    scored, estimated = con.sql(
        "SELECT (SELECT count(*) FROM truth), (SELECT count(DISTINCT (trip_id, stop_sequence)) FROM result)"
    ).fetchone()
    print(f"{service_date}: {scored:,} hidden, {estimated:,} estimated at some gap")


def summarise(out: Path) -> None:
    files = sorted(out.glob("hide_and_compare_*.parquet"))
    con = duckdb.connect()
    con.execute(
        f"""
        CREATE TABLE r AS
        SELECT *, est - actual AS signed,
               actual - scheduled AS true_delay, est - scheduled AS est_delay
        FROM read_parquet({[str(f) for f in files]!r})
    """
    )
    on = f"BETWEEN {ONTIME_FROM} AND {ONTIME_TO}"
    columns = f"""
        count(*) AS n,
        round(median(signed), 1) AS med_signed,
        round(avg(signed), 1) AS mean_signed,
        round(median(abs(signed)), 1) AS med_abs,
        round(quantile_cont(abs(signed), 0.9), 1) AS p90_abs,
        round(quantile_cont(abs(signed), 0.99), 1) AS p99_abs,
        round(100.0 * count(*) FILTER (WHERE (true_delay {on}) <> (est_delay {on})) / count(*), 2)
            AS pct_other_side,
        round(100.0 * count(*) FILTER (WHERE true_delay {on}) / count(*), 2) AS ontime_true,
        round(100.0 * count(*) FILTER (WHERE est_delay {on}) / count(*), 2) AS ontime_est
    """
    days = len(files)
    total, estimated = con.sql("SELECT count(*), count(est) FROM r").fetchone()
    print(f"{days} days, {total:,} stops with a STOPPED_AT report hidden, {estimated:,} estimated")
    for name, where in (("every hidden stop", "true"), ("dwell of 10 s or less", "dwell <= 10")):
        print(f"\n== {name}, by the gap between the two reports")
        show(
            con,
            f"SELECT limit_s, {columns} FROM r WHERE est IS NOT NULL AND {where} GROUP BY 1 ORDER BY 1",
            by_limit=True,
        )
        for limit in LIMITS[:-1] + (None,):
            bound = "" if limit is None else f"AND limit_s <= {limit}"
            label = "any gap" if limit is None else f"gap up to {limit} s"
            print(f"-- {label}")
            show(con, f"SELECT {columns} FROM r WHERE est IS NOT NULL AND {where} {bound}")
    print("\n== direction of the flips, dwell of 10 s or less, gap up to 300 s")
    show(
        con,
        f"""SELECT count(*) FILTER (WHERE (true_delay {on}) AND NOT (est_delay {on})) true_on_est_off,
                   count(*) FILTER (WHERE NOT (true_delay {on}) AND (est_delay {on})) true_off_est_on
            FROM r WHERE est IS NOT NULL AND dwell <= 10 AND limit_s <= 300""",
    )


def show(con: duckdb.DuckDBPyConnection, query: str, by_limit: bool = False) -> None:
    relation = con.sql(query)
    print(" | ".join(relation.columns))
    for row in relation.fetchall():
        cells = [str(v) for v in row]
        if by_limit:
            cells[0] = LABELS[row[0]]
        print(" | ".join(cells))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    one = commands.add_parser("grade")
    one.add_argument("days", nargs="+", help="service days as YYYYMMDD")
    one.add_argument("--raw-dir", type=Path, required=True)
    one.add_argument("--cache", type=Path, required=True)
    one.add_argument("--out", type=Path, required=True)
    two = commands.add_parser("summarise")
    two.add_argument("out", type=Path)
    args = parser.parse_args()
    if args.command == "grade":
        for day in args.days:
            grade(day, args.raw_dir, args.cache, args.out)
    else:
        summarise(args.out)
