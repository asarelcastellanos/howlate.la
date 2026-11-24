"""Grade one day twice, with the rail matcher off and on, and compare. Uploads nothing.

Run on the backfill VM as

    python pipeline/scripts/rail_regrade.py --service-date YYYYMMDD --cache DIR --out DIR

or on local files with no bucket access

    python pipeline/scripts/rail_regrade.py --service-date YYYYMMDD --out DIR --cache DIR \
        --raw-dir RAW --gtfs-dir GTFS

where GTFS holds gtfs_bus/ and gtfs_rail/ already unpacked.

Both gradings use the same raw files and timetable, so the only difference is
`railmatch.ENABLED`. Each writes its day to OUT/before and OUT/after, as
`arrivals` does without uploading. On the VM the published report for the day
is read as well, which is a small read of one JSON file.

A third pass counts what became of the trip ids that sit only under later-start
services (#166). A trip id counts as graded when one of its rows moved to a
fitted trip. Otherwise it is ungraded, for the first reason that holds of its
rows. A row in a run the matcher trusts keeps its id, a row in a run that did not
fit confidently is dropped, a row in a matched run is dropped when the fitted trip
has no stop with its stop_id, and a row in no run is dropped.

Writes OUT/rail_regrade_DAY.json and prints the same numbers.
"""

import argparse
import json
import sys
import time
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from howlate_pipeline import DERIVED_BUCKET, RAIL_AGENCY, arrivals, gtfs, railmatch  # noqa: E402
from howlate_pipeline.__main__ import Bucket, grade_day, local_timetables  # noqa: E402

KEYS = ["coverage", "median_delay_min", "absurd_pct", "rail_misfit_pct", "matched_rate"]


def per_line(path: Path) -> dict:
    """Each rail line's scheduled stops, coverage, median delay and share beyond an hour."""
    rows = (
        duckdb.connect()
        .execute(
            """
        SELECT line, count(*),
               count(*) FILTER (WHERE source NOT IN ('none', 'interpolated')),
               median(delay_seconds) FILTER (WHERE NOT is_origin),
               count(*) FILTER (WHERE abs(delay_seconds) > 3600),
               count(*) FILTER (WHERE delay_seconds IS NOT NULL)
        FROM read_parquet(?) WHERE agency = ? GROUP BY ROLLUP (line) ORDER BY line NULLS LAST
    """,
            [str(path), RAIL_AGENCY],
        )
        .fetchall()
    )
    return {
        line or "all": {
            "scheduled": scheduled,
            "measured": measured,
            "coverage_pct": round(100 * measured / scheduled, 1) if scheduled else 0.0,
            "median_delay_min": None if median is None else round(median / 60, 2),
            "beyond_hour": beyond,
            "timed": timed,
            "beyond_hour_pct": round(100 * beyond / timed, 2) if timed else 0.0,
        }
        for line, scheduled, measured, median, beyond, timed in rows
    }


def graded(out: Path, service_date: str) -> dict:
    report = json.loads(
        (out / arrivals.partition("reports", service_date) / "report.json").read_text()
    )
    path = out / arrivals.partition("arrivals", service_date) / "part-0.parquet"
    return {
        "stats": {key: report["stats"][key] for key in KEYS},
        "rail_misfits": report["rail_misfits"],
        "rail_matching": report.get("rail_matching", []),
        "rail": per_line(path),
    }


def fates(service_date: str, files: list[str], timetable) -> dict:
    """What became of each trip id that sits only under later-start services."""
    con = arrivals.connect()
    arrivals.load_observations(con, files, service_date)
    read: dict = {}
    directories = timetable(arrivals.observed_trip_ids(con), read)
    arrivals.load_schedule(con, directories, service_date, read)
    con.execute(
        """
        CREATE TABLE later_rows AS
        SELECT o.vehicle_id, o.ts, o.status, o.stop_id, o.trip_id FROM observations o
        JOIN (SELECT trip_id FROM listed_trips WHERE agency = ?
              GROUP BY trip_id HAVING NOT bool_or(service_active) AND bool_and(service_later)) l
          USING (trip_id)
        WHERE o.agency = ?
    """,
        [RAIL_AGENCY, RAIL_AGENCY],
    )
    rail_rows = con.execute(
        "SELECT count(*) FROM observations WHERE agency = ?", [RAIL_AGENCY]
    ).fetchone()[0]
    started = time.monotonic()
    arrivals.match_rail_runs(con, directories, service_date)
    seconds = round(time.monotonic() - started)
    kept = con.execute(
        "SELECT count(*) FROM observations WHERE agency = ?", [RAIL_AGENCY]
    ).fetchone()[0]

    reason = con.execute(
        """
        WITH fate AS (
            SELECT l.trip_id,
                   CASE
                     WHEN EXISTS (SELECT 1 FROM observations o
                                  WHERE o.vehicle_id = l.vehicle_id AND o.ts = l.ts
                                    AND o.status = l.status AND o.stop_id = l.stop_id
                                    AND o.trip_id <> l.trip_id) THEN 'graded'
                     WHEN EXISTS (SELECT 1 FROM observations o
                                  WHERE o.vehicle_id = l.vehicle_id AND o.ts = l.ts
                                    AND o.status = l.status AND o.stop_id = l.stop_id
                                    AND o.trip_id = l.trip_id) THEN 'kept_in_a_trusted_run'
                     WHEN r.outcome = 'ungraded' THEN 'run_not_confident'
                     WHEN r.outcome = 'matched' THEN 'no_such_stop_on_fitted_trip'
                     ELSE 'in_no_run'
                   END AS fate
            FROM later_rows l
            LEFT JOIN (SELECT vehicle_id, run_start, run_end, outcome FROM rail_runs) r
              ON r.vehicle_id = l.vehicle_id AND l.ts BETWEEN r.run_start - ? AND r.run_end + ?
        ),
        best AS (
            SELECT trip_id, min(CASE fate WHEN 'graded' THEN 0 WHEN 'kept_in_a_trusted_run' THEN 1
                                WHEN 'run_not_confident' THEN 2
                                WHEN 'no_such_stop_on_fitted_trip' THEN 3 ELSE 4 END) AS rank
            FROM fate GROUP BY trip_id
        )
        SELECT CASE rank WHEN 0 THEN 'graded' WHEN 1 THEN 'kept_in_a_trusted_run'
                         WHEN 2 THEN 'run_not_confident' WHEN 3 THEN 'no_such_stop_on_fitted_trip'
                         ELSE 'in_no_run' END, count(*)
        FROM best GROUP BY ALL ORDER BY 1
    """,
        [railmatch.LAYOVER_S, railmatch.GAP_S],
    ).fetchall()
    counts = dict(reason)
    return {
        "later_start_trips": sum(counts.values()),
        "graded_through_the_matcher": counts.get("graded", 0),
        "ungraded": {k: v for k, v in counts.items() if k != "graded"},
        "rail_rows_before": rail_rows,
        "rail_rows_after": kept,
        "match_rail_runs_seconds": seconds,
    }


def regrade(args: argparse.Namespace) -> None:
    service_date = args.service_date
    bucket = Bucket()
    local = args.raw_dir is not None
    timetables = local_timetables(args.gtfs_dir, upload=False) if local else None

    if local:
        files = arrivals.local_files(args.raw_dir, service_date)

        def timetable(_, read):
            return timetables
    else:
        files = arrivals.fetch_raw(bucket(), service_date, args.cache)

        def timetable(observed, read):
            return gtfs.prepare(bucket(), service_date, args.cache / "gtfs", observed, read)

    if not files:
        sys.exit(f"no raw files found for {service_date}")

    result: dict = {"service_date": service_date}
    for label, enabled in (("before", False), ("after", True)):
        railmatch.ENABLED = enabled
        grade_day(
            bucket,
            service_date,
            cache=args.cache,
            out=args.out / label,
            raw_dir=args.raw_dir,
            timetables=timetables,
            upload=False,
        )
        result[label] = graded(args.out / label, service_date)
    railmatch.ENABLED = True
    result["later_start_trips"] = fates(service_date, files, timetable)

    if not local:
        day = f"{service_date[:4]}-{service_date[4:6]}-{service_date[6:]}"
        blob = (
            bucket()
            .bucket(DERIVED_BUCKET)
            .blob(f"{arrivals.partition('reports', service_date)}report.json")
        )
        published = json.loads(blob.download_as_text())
        result["published"] = {
            "service_date": day,
            "pipeline_version": published["pipeline_version"],
            "stats": {key: published["stats"].get(key) for key in KEYS},
            "rail_misfits": published.get("rail_misfits"),
        }

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / f"rail_regrade_{service_date}.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--service-date", required=True, help="YYYYMMDD")
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--raw-dir", type=Path, help="read raw files from here, no bucket")
    parser.add_argument("--gtfs-dir", type=Path, help="gtfs_bus/ and gtfs_rail/, needs --raw-dir")
    args = parser.parse_args()
    if bool(args.raw_dir) != bool(args.gtfs_dir):
        sys.exit("--raw-dir and --gtfs-dir go together")
    regrade(args)


if __name__ == "__main__":
    main()
