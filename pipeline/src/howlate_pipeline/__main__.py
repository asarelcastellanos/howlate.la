"""Grade days and summarise them, one at a time or on a schedule.

    python -m howlate_pipeline arrivals --service-date 2026-08-18
    python -m howlate_pipeline aggregate --from-bucket
    python -m howlate_pipeline backfill --from 2026-08-18 --to 2026-11-07
    python -m howlate_pipeline daily

`arrivals` reads the raw archive and the timetable in force and writes one
Parquet partition per table, arrivals and trips, then the day's report. It
handles one day, and rerunning a day replaces that day and touches nothing
else, so any day can be recomputed at any time.

`aggregate` reads every partition of one layout version and produces the small
JSON files a browser fetches. It handles all days at once, because a median over
one Tuesday is not an answer to "is my bus usually late".

`backfill` runs `arrivals` over a range, skipping days already done; see
backfill.py for its rules. `daily` is what the scheduled job runs: a short
backfill over the last few days, then `aggregate` over everything graded.

`arrivals` with --raw-dir, --gtfs-dir and --no-upload, and `aggregate` with
--gtfs-dir and --no-upload, touch no Cloud Storage, so both run on local files
without credentials. `backfill` and `daily` always read the buckets.
"""

import argparse
import os
import sys
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

from google.cloud import storage

from howlate_pipeline import (
    DERIVED_BUCKET,
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


def require_complete(service_date: str) -> str:
    """The day as YYYYMMDD, refused if the archive is still being written for it.

    Graded early a day would be missing its evening, and its saved report would
    stop it ever being graded again.
    """
    day = backfill.parse_day(service_date)
    latest = backfill.parse_day(yesterday())
    if day > latest:
        sys.exit(f"{day:%Y-%m-%d} is not complete yet; the latest is {latest:%Y-%m-%d}")
    return f"{day:%Y%m%d}"


class Bucket:
    """A Cloud Storage client made only when something needs one.

    Grading one day from a local raw directory and local timetables, without
    uploading, needs no credentials at all, which is what lets CI run
    `arrivals` and `aggregate` inside the container.
    """

    def __init__(self) -> None:
        self._client: storage.Client | None = None

    def __call__(self) -> storage.Client:
        if self._client is None:
            self._client = storage.Client()
        return self._client


def local_timetables(directory: Path | None, upload: bool) -> dict[str, Path] | None:
    """Timetables already unpacked under DIR/gtfs_bus and DIR/gtfs_rail.

    Only for local runs. These skip the archive's checks that the timetable is
    the one in force that day and that both feeds are there, so a day graded
    with them must never reach the bucket, where its report would mark the day
    done for good.
    """
    if directory is None:
        return None
    if upload:
        sys.exit("--gtfs-dir is only for local runs; add --no-upload")
    found = {
        agency: directory / feed
        for feed, agency in gtfs.FEEDS.items()
        if (directory / feed / "stop_times.txt").exists()
    }
    if not found:
        sys.exit(f"no gtfs_bus/ or gtfs_rail/ timetable under {directory}")
    return found


def run_arrivals(args: argparse.Namespace) -> int:
    # The day is checked before a client is made, so refusing a day needs no
    # credentials.
    day = require_complete(args.service_date)
    return grade_day(
        Bucket(),
        day,
        cache=args.cache,
        out=args.out,
        raw_dir=args.raw_dir,
        timetables=local_timetables(args.gtfs_dir, upload=not args.no_upload),
        upload=not args.no_upload,
    )


def grade_day(
    bucket: Bucket,
    service_date: str,
    *,
    cache: Path,
    out: Path,
    raw_dir: Path | None = None,
    timetables: dict[str, Path] | None = None,
    upload: bool = True,
) -> int:
    """Grade one service day, write it, and upload it unless told not to."""
    started = time.monotonic()

    print("raw archive:")
    if raw_dir:
        files = arrivals.local_files(raw_dir, service_date)
        print(f"  raw: {len(files)} files from {raw_dir}")
    else:
        files = arrivals.fetch_raw(bucket(), service_date, cache)
    if not files:
        sys.exit(f"no raw files found for {service_date}")

    con = arrivals.connect()
    arrivals.load_observations(con, files, service_date)

    # After the observations, because the timetable is chosen by how many of the
    # reported trip_ids it holds. Before any download, so a day with no raw files
    # costs no timetable.
    print(f"timetables for {service_date}:")
    directories = timetables or gtfs.prepare(
        bucket(), service_date, cache / "gtfs", arrivals.observed_trip_ids(con)
    )
    arrivals.load_schedule(con, directories, service_date)
    arrivals.match(con, service_date)
    arrivals.trips(con)

    # The old report goes first. Until the new one is saved, nothing on disk
    # may claim this day is finished.
    (out / report_path(service_date)).unlink(missing_ok=True)
    written = arrivals.write(con, out, service_date)
    path = written["arrivals"]
    size = path.stat().st_size
    rows = con.sql("SELECT count(*) FROM arrivals").fetchone()[0]

    report.show(con, service_date)
    # Saved last so that, in the bucket, a report is the sign a day finished.
    saved = report.document(con, service_date)
    written["reports"] = report.save(saved, out / report_path(service_date))
    print(
        f"\n  wrote {path} ({size / 1e6:.1f} MB, {rows:,} rows, "
        f"{size / rows if rows else 0:.1f} bytes/row) in {time.monotonic() - started:.0f}s"
    )

    if upload:
        for where in arrivals.upload(bucket(), written, service_date):
            print(f"  uploaded {where}")

    # A failed check is not a failed run: the day's numbers are written either
    # way. The status is here so a scheduler shows a red job rather than burying
    # a drifting feed in a log nobody reads.
    return 0 if saved["ok"] else 2


def report_path(day: str) -> str:
    """Where a day's report lives, relative to the output root or the bucket."""
    return arrivals.partition("reports", day) + "report.json"


def report_exists(bucket: Bucket, out: Path, upload: bool):
    """The Done rule: a day is done when its report exists, in the bucket or,
    without uploading, on disk."""

    def is_done(day: str) -> bool:
        if upload:
            return bucket().bucket(DERIVED_BUCKET).blob(report_path(day)).exists()
        return (out / report_path(day)).exists()

    return is_done


def run_backfill(args: argparse.Namespace) -> int:
    last = require_complete(args.last)
    days = backfill.days_between(args.first, last)
    bucket = Bucket()
    upload = not args.no_upload

    result = backfill.run(
        days,
        grade=lambda day: grade_day(bucket, day, cache=args.cache, out=args.out, upload=upload),
        is_done=report_exists(bucket, args.out, upload),
        after_day=lambda day: backfill.prune_cache(args.cache, day),
    )
    return backfill.exit_code(result)


def heartbeat(ok: bool, summary: str) -> None:
    """Tell healthchecks.io how the run went, if a URL is set.

    Silence is the alarm for a job that never ran; /fail is the alarm for one
    that ran and went wrong. The URL is a secret and comes from the job's
    environment. A failed ping is printed and ignored, because the run's own
    result matters more than the report about it. Only the error's type is
    printed: urllib puts the URL, and so the secret, in its messages.
    """
    # A secret saved with `echo` ends in a newline, which breaks only /fail.
    url = os.environ.get("HOWLATE_HEARTBEAT_URL", "").strip()
    if not url:
        return
    try:
        request = urllib.request.Request(
            url if ok else f"{url}/fail", data=summary.encode()[:10_000], method="POST"
        )
        urllib.request.urlopen(request, timeout=10).close()
    except Exception as error:
        print(f"  heartbeat failed: {type(error).__name__}")


def run_daily(args: argparse.Namespace) -> int:
    """Grade the last few days not yet done, then rebuild the site.

    Catching up over several days rather than grading only yesterday means a
    missed run, or a day that failed, is picked up by the next one without
    anyone doing anything.

    The site is rebuilt even when a day errored, from the days that finished,
    and the heartbeat still reports the failure. A day that fails every time,
    such as one the collector missed, would otherwise hold back every newer day
    for as long as it stays in the window. A failed day adds nothing to the
    site, because only days with a report are summarised. A failure while
    uploading the site leaves the last complete one published; see
    aggregate.upload.
    """
    # Set in the image, so each run's log shows which code it ran.
    print(f"howlate-pipeline at commit {os.environ.get('HOWLATE_COMMIT', 'unknown')}")
    last = backfill.parse_day(yesterday())
    first = last - timedelta(days=args.catch_up - 1)
    bucket = Bucket()
    try:
        result = backfill.run(
            backfill.days_between(f"{first:%Y%m%d}", f"{last:%Y%m%d}"),
            grade=lambda day: grade_day(bucket, day, cache=args.cache, out=args.out),
            is_done=report_exists(bucket, args.out, upload=True),
            after_day=lambda day: backfill.prune_cache(args.cache, day),
        )
        code = backfill.exit_code(result)
        summary = ", ".join(f"{key} {len(days)}" for key, days in result.items())
        graded = args.cache / "graded" / arrivals.VERSION
        if not aggregate.fetch_arrivals(bucket(), graded):
            # No day of this layout version has finished yet, as on a first
            # deploy or after a version bump. The day counts say more than the
            # error `aggregate` would raise over an empty directory.
            heartbeat(False, f"no finished day to publish: {summary}")
            return code or 1
        build_site(bucket, graded, cache=args.cache, out=args.out / "site")
    except BaseException as error:
        heartbeat(False, f"daily run crashed: {error!r}")
        raise

    heartbeat(code == 0, summary)
    return code


def run_aggregate(args: argparse.Namespace) -> int:
    bucket = Bucket()
    # Before any download, so a refused run costs nothing.
    timetables = local_timetables(args.gtfs_dir, upload=not args.no_upload)
    graded = args.arrivals or Path(f"out/arrivals/{arrivals.VERSION}")
    if args.from_bucket:
        # A directory of its own under the cache, because fetching empties it
        # first, and --arrivals may hold days graded locally and never uploaded.
        graded = args.cache / "graded" / arrivals.VERSION
        aggregate.fetch_arrivals(bucket(), graded)
    return build_site(
        bucket,
        graded,
        cache=args.cache,
        out=args.out,
        timetables=timetables,
        upload=not args.no_upload,
    )


def build_site(
    bucket: Bucket,
    arrivals_dir: Path,
    *,
    cache: Path,
    out: Path,
    timetables: dict[str, Path] | None = None,
    upload: bool = True,
) -> int:
    """Summarise every graded day into the site's JSON, and upload it."""
    started = time.monotonic()
    con = arrivals.connect()

    first, last, days = aggregate.load(con, arrivals_dir)
    print(f"{days} service day(s) collected, {first} to {last}")
    if days < 20:
        # Said plainly rather than hidden, because every median below rests on it.
        print(
            f"  NOTE only {days} day(s) of data. Roughly a month is where "
            f"patterns separate from noise, so treat these as provisional."
        )

    print("labels:")
    directories = timetables or gtfs.prepare(bucket(), last.replace("-", ""), cache / "gtfs")
    catalogue = labels.load(con, directories)
    print(
        f"  {len(catalogue['lines'])} lines, {len(catalogue['directions'])} directions, "
        f"{len(catalogue['stops']):,} stops named"
    )

    written = aggregate.build(con, catalogue, out, first, last, days)
    biggest = max(written, key=lambda row: row[2])
    total = sum(row[1] for row in written)

    print(f"\n  wrote {len(written)} line files + index.json + status.json to {out}")
    print(
        f"  {total / 1e6:.2f} MB total, largest is line {biggest[0]} at "
        f"{biggest[1] / 1e3:.0f} KB ({biggest[2] / 1e3:.0f} KB gzipped)"
    )
    if upload:
        count, where = aggregate.upload(bucket(), out)
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
    one.add_argument(
        "--gtfs-dir",
        type=Path,
        help="unpacked timetables under DIR/gtfs_bus and DIR/gtfs_rail, instead of the archive",
    )
    one.set_defaults(run=run_arrivals)

    daily = jobs.add_parser(
        "daily", parents=[shared], help="grade recent days not yet done, then rebuild the site"
    )
    daily.add_argument(
        "--catch-up",
        type=int,
        default=7,
        help="how many days back to look for ungraded days (default 7)",
    )
    daily.add_argument("--out", type=Path, default=Path("out"), help="where working files go")
    daily.set_defaults(run=run_daily)

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
    many.set_defaults(run=run_backfill)

    every = jobs.add_parser(
        "aggregate", parents=[shared], help="summarise every day measured so far"
    )
    source = every.add_mutually_exclusive_group()
    source.add_argument(
        "--arrivals",
        type=Path,
        help=f"one version's partitions (default out/arrivals/{arrivals.VERSION})",
    )
    every.add_argument("--out", type=Path, default=Path("site"), help="where the JSON goes")
    every.add_argument(
        "--no-upload",
        action="store_true",
        help="write locally without pushing to the derived bucket",
    )
    every.add_argument(
        "--gtfs-dir",
        type=Path,
        help="unpacked timetables under DIR/gtfs_bus and DIR/gtfs_rail, instead of the archive",
    )
    source.add_argument(
        "--from-bucket",
        action="store_true",
        help="summarise every graded day in the derived bucket, downloaded under --cache",
    )
    every.set_defaults(run=run_aggregate)

    args = parser.parse_args()
    sys.exit(args.run(args))


if __name__ == "__main__":
    main()
