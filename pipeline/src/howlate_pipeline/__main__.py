"""Two jobs: measure one day, then summarise every day measured so far.

    python -m howlate_pipeline arrivals --service-date 2026-08-18
    python -m howlate_pipeline aggregate

`arrivals` reads the raw archive and the timetable in force and writes one
Parquet partition. It handles one day, and rerunning a day replaces that day and
touches nothing else, so any day can be recomputed at any time.

`aggregate` reads every partition written so far and produces the small JSON
files a browser fetches. It handles all days at once, because a median over one
Tuesday is not an answer to "is my bus usually late".
"""

import argparse
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from google.cloud import storage

from howlate_pipeline import aggregate, arrivals, gtfs, labels, report


def yesterday() -> str:
    """The default day to measure.

    Two days back, not one. A service day is not over until about 3am the
    following morning, and the UTC partition holding its evening is only complete
    once that morning has passed.
    """
    return (datetime.now() - timedelta(days=2)).strftime("%Y%m%d")


def run_arrivals(args: argparse.Namespace) -> int:
    service_date = args.service_date.replace("-", "")
    started = time.monotonic()
    client = storage.Client()

    print(f"timetables in force on {service_date}:")
    directories = gtfs.prepare(client, service_date, args.cache / "gtfs")

    print("raw archive:")
    if args.raw_dir:
        files = arrivals.local_files(args.raw_dir, service_date)
        print(f"  raw: {len(files)} files from {args.raw_dir}")
    else:
        files = arrivals.fetch_raw(client, service_date, args.cache)
    if not files:
        sys.exit(f"no raw files found for {service_date}")

    con = arrivals.connect()
    arrivals.load_observations(con, files, service_date)
    arrivals.load_schedule(con, directories, service_date)
    arrivals.match(con, service_date)

    path = arrivals.write(con, args.out, service_date)
    size = path.stat().st_size
    rows = con.sql("SELECT count(*) FROM arrivals").fetchone()[0]

    ok = report.show(con, service_date)
    print(f"\n  wrote {path} ({size / 1e6:.1f} MB, {rows:,} rows, "
          f"{size / rows:.1f} bytes/row) in {time.monotonic() - started:.0f}s")

    if not args.no_upload:
        print(f"  uploaded {arrivals.upload(client, path, service_date)}")

    # A failed check is not a failed run: the day's numbers are written either
    # way. The status is here so a scheduler shows a red job rather than burying
    # a drifting feed in a log nobody reads.
    return 0 if ok else 2


def run_aggregate(args: argparse.Namespace) -> int:
    started = time.monotonic()
    con = arrivals.connect()

    first, last, days = aggregate.load(con, args.arrivals)
    print(f"{days} service day(s) collected, {first} to {last}")
    if days < 20:
        # Said plainly rather than hidden, because every median below rests on it.
        print(f"  NOTE only {days} day(s) of data. Roughly a month is where "
              f"patterns separate from noise, so treat these as provisional.")

    print("labels:")
    client = storage.Client()
    directories = gtfs.prepare(client, last.replace("-", ""), args.cache / "gtfs")
    catalogue = labels.load(con, directories)
    print(f"  {len(catalogue['lines'])} lines, {len(catalogue['directions'])} directions, "
          f"{len(catalogue['stops']):,} stops named")

    written = aggregate.build(con, catalogue, args.out, first, last, days)
    biggest = max(written, key=lambda row: row[2])
    total = sum(row[1] for row in written)

    print(f"\n  wrote {len(written)} line files + index.json + status.json to {args.out}")
    print(f"  {total / 1e6:.2f} MB total, largest is line {biggest[0]} at "
          f"{biggest[1] / 1e3:.0f} KB ({biggest[2] / 1e3:.0f} KB gzipped)")
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
    shared.add_argument("--cache", type=Path, default=Path(".cache"),
                        help="where downloaded raw files and timetables are kept")

    one = jobs.add_parser("arrivals", parents=[shared], help="measure one service day")
    one.add_argument("--service-date", default=yesterday(),
                     help="YYYY-MM-DD or YYYYMMDD. Defaults to two days ago.")
    one.add_argument("--out", type=Path, default=Path("out"), help="where the Parquet goes")
    one.add_argument("--raw-dir", type=Path,
                     help="read raw files from here instead of Cloud Storage")
    one.add_argument("--no-upload", action="store_true",
                     help="write locally without pushing to the derived bucket")
    one.set_defaults(run=run_arrivals)

    every = jobs.add_parser("aggregate", parents=[shared], help="summarise every day measured so far")
    every.add_argument("--arrivals", type=Path, default=Path("out/arrivals"),
                       help="where the Parquet partitions are")
    every.add_argument("--out", type=Path, default=Path("site"),
                       help="where the JSON goes")
    every.add_argument("--no-upload", action="store_true",
                       help="write locally without pushing to the derived bucket")
    every.set_defaults(run=run_aggregate)

    args = parser.parse_args()
    sys.exit(args.run(args))


if __name__ == "__main__":
    main()
