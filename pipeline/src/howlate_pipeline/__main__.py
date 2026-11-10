"""Two jobs: measure one day, then summarise every day measured so far.

    python -m howlate_pipeline arrivals --service-date 2026-08-18
    python -m howlate_pipeline aggregate

`arrivals` reads the raw archive and the timetable in force and writes one
Parquet partition per table, arrivals and trips. It handles one day, and
rerunning a day replaces that day and touches nothing else, so any day can be
recomputed at any time.

`aggregate` reads every partition of one layout version and produces the small
JSON files a browser fetches. It handles all days at once, because a median over one
Tuesday is not an answer to "is my bus usually late".
"""

import argparse
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from google.cloud import storage

from howlate_pipeline import (
    DERIVED_BUCKET,
    __version__,
    aggregate,
    arrivals,
    backfill,
    gtfs,
    labels,
    report,
)


def yesterday() -> str:
    """The default day to measure.

    Two days back, not one. A service day is not over until about 3am the
    following morning, and the UTC partition holding its evening is only complete
    once that morning has passed.
    """
    return (datetime.now() - timedelta(days=2)).strftime("%Y%m%d")


def run_arrivals(args: argparse.Namespace) -> int:
    return grade_day(
        storage.Client(),
        args.service_date.replace("-", ""),
        cache=args.cache,
        out=args.out,
        raw_dir=args.raw_dir,
        upload=not args.no_upload,
    )


def grade_day(
    client: storage.Client,
    service_date: str,
    *,
    cache: Path,
    out: Path,
    raw_dir: Path | None = None,
    upload: bool = True,
) -> int:
    """Grade one service day, write it, and upload it unless told not to."""
    started = time.monotonic()

    print(f"timetables in force on {service_date}:")
    directories = gtfs.prepare(client, service_date, cache / "gtfs")

    print("raw archive:")
    if raw_dir:
        files = arrivals.local_files(raw_dir, service_date)
        print(f"  raw: {len(files)} files from {raw_dir}")
    else:
        files = arrivals.fetch_raw(client, service_date, cache)
    if not files:
        sys.exit(f"no raw files found for {service_date}")

    con = arrivals.connect()
    arrivals.load_observations(con, files, service_date)
    arrivals.load_schedule(con, directories, service_date)
    arrivals.match(con, service_date)
    arrivals.trips(con)

    # The old report goes first. Until the new one is saved, nothing on disk
    # may claim this day is finished.
    (out / arrivals.partition("reports", service_date) / "report.json").unlink(missing_ok=True)
    written = arrivals.write(con, out, service_date)
    path = written["arrivals"]
    size = path.stat().st_size
    rows = con.sql("SELECT count(*) FROM arrivals").fetchone()[0]

    report.show(con, service_date)
    # Saved last so that, in the bucket, a report is the sign a day finished.
    saved = report.document(con, service_date)
    written["reports"] = report.save(
        saved, out / arrivals.partition("reports", service_date) / "report.json"
    )
    print(
        f"\n  wrote {path} ({size / 1e6:.1f} MB, {rows:,} rows, "
        f"{size / rows if rows else 0:.1f} bytes/row) in {time.monotonic() - started:.0f}s"
    )

    if upload:
        for where in arrivals.upload(client, written, service_date):
            print(f"  uploaded {where}")

    # A failed check is not a failed run: the day's numbers are written either
    # way. The status is here so a scheduler shows a red job rather than burying
    # a drifting feed in a log nobody reads.
    return 0 if saved["ok"] else 2


def run_backfill(args: argparse.Namespace) -> int:
    if args.last.replace("-", "") > yesterday():
        # A later day is still being written to the archive. Graded now it
        # would be missing its evening, and its report would stop it ever
        # being graded again.
        sys.exit(f"--to {args.last} is not complete yet; the latest is {yesterday()}")

    client = storage.Client()
    upload = not args.no_upload

    def read_report(day: str) -> str | None:
        name = arrivals.partition("reports", day) + "report.json"
        if upload:
            blob = client.bucket(DERIVED_BUCKET).blob(name)
            return blob.download_as_text() if blob.exists() else None
        path = args.out / name
        return path.read_text() if path.exists() else None

    is_done = backfill.done_check(read_report, args.regrade, __version__)

    result = backfill.run(
        backfill.days_between(args.first, args.last),
        grade=lambda day: grade_day(client, day, cache=args.cache, out=args.out, upload=upload),
        is_done=is_done,
        after_day=lambda day: backfill.prune_cache(args.cache, day),
    )
    return backfill.exit_code(result)


def run_aggregate(args: argparse.Namespace) -> int:
    started = time.monotonic()
    con = arrivals.connect()

    first, last, days = aggregate.load(con, args.arrivals)
    print(f"{days} service day(s) collected, {first} to {last}")
    if days < 20:
        # Said plainly rather than hidden, because every median below rests on it.
        print(
            f"  NOTE only {days} day(s) of data. Roughly a month is where "
            f"patterns separate from noise, so treat these as provisional."
        )

    print("labels:")
    client = storage.Client()
    directories = gtfs.prepare(client, last.replace("-", ""), args.cache / "gtfs")
    catalogue = labels.load(con, directories)
    print(
        f"  {len(catalogue['lines'])} lines, {len(catalogue['directions'])} directions, "
        f"{len(catalogue['stops']):,} stops named"
    )

    written = aggregate.build(con, catalogue, args.out, first, last, days)
    biggest = max(written, key=lambda row: row[2])
    total = sum(row[1] for row in written)

    print(f"\n  wrote {len(written)} line files + index.json + status.json to {args.out}")
    print(
        f"  {total / 1e6:.2f} MB total, largest is line {biggest[0]} at "
        f"{biggest[1] / 1e3:.0f} KB ({biggest[2] / 1e3:.0f} KB gzipped)"
    )
    if not args.no_upload:
        count, where = aggregate.upload(storage.Client(), args.out)
        print(f"  uploaded {count} files to {where}")

    print(f"  in {time.monotonic() - started:.0f}s")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="howlate_pipeline", description=__doc__)
    jobs = parser.add_subparsers(dest="job", required=True)

    # Shared rather than global: argparse only accepts a parent's options before
    # the subcommand, which reads backwards for anyone typing the obvious thing.
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument(
        "--cache",
        type=Path,
        default=Path(".cache"),
        help="where downloaded raw files and timetables are kept",
    )

    one = jobs.add_parser("arrivals", parents=[shared], help="measure one service day")
    one.add_argument(
        "--service-date",
        default=yesterday(),
        help="YYYY-MM-DD or YYYYMMDD. Defaults to two days ago.",
    )
    one.add_argument("--out", type=Path, default=Path("out"), help="where the Parquet goes")
    one.add_argument(
        "--raw-dir", type=Path, help="read raw files from here instead of Cloud Storage"
    )
    one.add_argument(
        "--no-upload",
        action="store_true",
        help="write locally without pushing to the derived bucket",
    )
    one.set_defaults(run=run_arrivals)

    many = jobs.add_parser(
        "backfill", parents=[shared], help="grade every day in a range not already done"
    )
    many.add_argument("--from", dest="first", required=True, help="first service day, YYYY-MM-DD")
    many.add_argument(
        "--to", dest="last", default=yesterday(), help="last service day. Defaults to two days ago."
    )
    many.add_argument("--out", type=Path, default=Path("out"), help="where the Parquet goes")
    many.add_argument(
        "--no-upload",
        action="store_true",
        help="write locally; a day counts as done when its report is on local disk",
    )
    many.add_argument(
        "--regrade",
        action="store_true",
        help="also regrade days whose report came from a different pipeline version",
    )
    many.set_defaults(run=run_backfill)

    every = jobs.add_parser(
        "aggregate", parents=[shared], help="summarise every day measured so far"
    )
    every.add_argument(
        "--arrivals",
        type=Path,
        default=Path(f"out/arrivals/{arrivals.VERSION}"),
        help="one version's partitions, e.g. out/arrivals/v2",
    )
    every.add_argument("--out", type=Path, default=Path("site"), help="where the JSON goes")
    every.add_argument(
        "--no-upload",
        action="store_true",
        help="write locally without pushing to the derived bucket",
    )
    every.set_defaults(run=run_aggregate)

    args = parser.parse_args()
    sys.exit(args.run(args))


if __name__ == "__main__":
    main()
