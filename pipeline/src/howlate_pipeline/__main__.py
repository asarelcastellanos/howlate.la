"""Grade days and summarise them, one at a time or on a schedule.

    python -m howlate_pipeline arrivals --service-date 2026-08-18
    python -m howlate_pipeline aggregate --from-bucket
    python -m howlate_pipeline backfill --from 2026-08-18 --to 2026-11-07
    python -m howlate_pipeline daily
    python -m howlate_pipeline publish-r2 [--run RUN]

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

Outside Google Cloud, `arrivals`, `backfill` and `daily` refuse to download raw
files that are not already in the cache, because internet egress costs about
$0.12 per GiB. `--allow-egress` on `arrivals` and `backfill` forces it.

`daily` ends by copying the run it published to Cloudflare R2, and `publish-r2`
does that copy for an existing run on demand; see r2.py. Neither runs `arrivals`
or `aggregate`. Without R2 settings in the environment `daily` skips the copy,
unless R2_REQUIRED is set, which makes missing settings fail the run. When
R2_PUBLIC_URL is set, `daily` then fetches the public data and checks that its
newest day is within a few days of today. With R2_REQUIRED set, a missing
R2_PUBLIC_URL fails the run. `publish-r2` does not read R2_PUBLIC_URL.
"""

import argparse
import os
import re
import sys
import time
import urllib.request
from datetime import UTC, datetime, timedelta
from datetime import time as clock_time
from pathlib import Path
from zoneinfo import ZoneInfo

from google.cloud import storage

from howlate_pipeline import (
    DERIVED_BUCKET,
    ZONE,
    aggregate,
    arrivals,
    backfill,
    gtfs,
    labels,
    r2,
    report,
)

# Measured 2026-11-13 to 2026-11-16: the last bus report for a service day came
# between 05:49 and 06:12 Pacific the next morning, because the timetable has
# bus stops until 29:45 (05:45). Files reach the archive a median 17 s and at
# most 36 s after their last record, and a vehicle's own timestamp can trail
# the collector by about 610 s. The scheduled run at 08:00 therefore starts
# about 1h45 after the last bus report. A manual run may start from 07:00, which
# is still 47 minutes after the latest of those reports. Grading at 05:00 left
# 283 and 472 bus arrivals ungraded on the two days compared (0.05 to 0.09
# percent), and a saved report stops a day being graded again.
DAY_COMPLETE_FROM = clock_time(7, 0)


def yesterday(now: datetime | None = None) -> str:
    """The default day to measure: the latest service day that is complete.

    That is one day back from 07:00 Pacific, and two days back before it, when
    yesterday's buses may still be running. The scheduled run is at 08:00, so it
    always gets one day back. The count starts from the Pacific date, because a
    manual run after 16:00 Pacific sees tomorrow's date on a UTC machine.
    """
    local = (now or datetime.now(UTC)).astimezone(ZoneInfo(ZONE))
    back = 1 if local.time() >= DAY_COMPLETE_FROM else 2
    return (local.date() - timedelta(days=back)).strftime("%Y%m%d")


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
        allow_egress=args.allow_egress,
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
    allow_egress: bool = False,
) -> int:
    """Grade one service day, write it, and upload it unless told not to."""
    started = time.monotonic()

    print("raw archive:")
    if raw_dir:
        files = arrivals.local_files(raw_dir, service_date)
        print(f"  raw: {len(files)} files from {raw_dir}")
    else:
        files = arrivals.fetch_raw(bucket(), service_date, cache, allow_egress)
    if not files:
        sys.exit(f"no raw files found for {service_date}")

    con = arrivals.connect()
    arrivals.load_observations(con, files, service_date)

    # After the observations, because the timetable is chosen by how many of the
    # reported trip_ids it holds. Before any download, so a day with no raw files
    # costs no timetable.
    print(f"timetables for {service_date}:")
    read: dict[str, list[Path]] = {}
    directories = timetables or gtfs.prepare(
        bucket(), service_date, cache / "gtfs", arrivals.observed_trip_ids(con), read
    )
    arrivals.load_schedule(con, directories, service_date, read)
    arrivals.match(con, service_date)
    arrivals.interpolate(con)
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
        grade=lambda day: grade_day(
            bucket,
            day,
            cache=args.cache,
            out=args.out,
            upload=upload,
            allow_egress=args.allow_egress,
        ),
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


# A URL runs to the next whitespace. Stopping at a quote or bracket left the tail
# of "https://x.com/a(b)?X-Goog-Signature=SECRET" in the ping, and a signed
# URL's secret is in that tail. Only a final . , : or ; stays out of the match,
# so "see https://x/y: denied" keeps its colon.
URL = re.compile(r"https?://\S*[^\s.,:;]", re.IGNORECASE)
GS_PATH = re.compile(r"gs://[^\s'\")>\]]*[^\s'\")>\].,:;]", re.IGNORECASE)
S3_PATH = re.compile(r"s3://[^\s'\")>\]]*[^\s'\")>\].,:;]", re.IGNORECASE)
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
LINE_LIMIT = 160


def redact(text: str) -> str:
    """Replace URLs, gs:// and s3:// paths and email addresses with fixed placeholders.

    Error text goes to healthchecks.io, a third party, and a Google API error
    names the service account and the bucket path. URLs go first, so an address
    inside one is not matched on its own. Schemes match in any case.

    A bare hostname, such as `acct.r2.cloudflarestorage.com` with no scheme, is
    not redacted. A pattern for one would also match file names, module paths
    and version numbers, and eat ordinary text.
    """
    text = URL.sub("<url>", text)
    text = GS_PATH.sub("<gs-path>", text)
    return EMAIL.sub("<email>", S3_PATH.sub("<s3-path>", text))


def first_line(text: str) -> str:
    """The first line of `text` that holds anything but whitespace."""
    return next((line.strip() for line in text.splitlines() if line.strip()), "")


def clip(line: str, limit: int = LINE_LIMIT) -> str:
    return line if len(line) <= limit else line[: limit - 3] + "..."


def failure_lines(failures: dict[str, BaseException], result: dict[str, list[str]]) -> list[str]:
    """One line for every failed day, in day order, each at most LINE_LIMIT characters.

    A day whose grading raised reads `<day> failed: <type>: <first line of the
    error>`. A day that only failed its checks, or only failed its cleanup, has
    no error text and reads `<day> failed its checks` or `<day> cleanup failed`.
    `backfill.run` keeps only day names, so these come from its result buckets.
    A day already named with its error is not named again.
    """
    lines = {}
    for day, error in failures.items():
        first = redact(first_line(str(error)))
        lines[day] = f"{day} failed: {type(error).__name__}" + (f": {first}" if first else "")
    labels: dict[str, list[str]] = {}
    for key, label in (
        ("checks_failed", "failed its checks"),
        ("errors", "errored"),
        ("cleanup_failed", "cleanup failed"),
    ):
        for day in result[key]:
            if day not in lines:
                labels.setdefault(day, []).append(label)
    lines.update({day: f"{day} {' and '.join(found)}" for day, found in labels.items()})
    return [clip(lines[day]) for day in sorted(lines)]


def ping_body(
    head: str,
    failures: dict[str, BaseException],
    result: dict[str, list[str]],
    limit: int = 1000,
) -> str:
    """The head, then every failed day, under `limit` characters.

    The counts in the head come first. When the days do not all fit, the body
    ends with `and N more days`, so a cut is never silent.
    """
    lines = failure_lines(failures, result)
    for kept in range(len(lines), -1, -1):
        left_out = len(lines) - kept
        more = [f"and {left_out} more day{'' if left_out == 1 else 's'}"] if left_out else []
        body = "\n".join(part for part in (head, *lines[:kept], *more) if part)
        if len(body) < limit:
            return body
    return body[: limit - 4] + "..."  # the head alone is too long


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

    The run the site published is then copied to R2. By then the graded days and
    the site in Cloud Storage are saved, so a failed copy changes nothing
    already written. It still fails the run and sends /fail, because the public
    site reads R2 and would otherwise go stale with nothing to say so. The same
    goes for R2 settings that are missing while R2_REQUIRED is set, and for a
    public address that does not serve the new run; see r2.probe.

    A failure ping names every failed day. A day whose grading raised comes with
    the first non-empty line of its error. When the days do not fit in the ping,
    it says how many it left out.
    """
    # Set in the image, so each run's log shows which code it ran.
    print(f"howlate-pipeline at commit {os.environ.get('HOWLATE_COMMIT', 'unknown')}")
    last = backfill.parse_day(yesterday())
    first = last - timedelta(days=args.catch_up - 1)
    bucket = Bucket()
    failures: dict[str, BaseException] = {}

    def grade(day: str) -> int:
        # backfill.run keeps only the day names, and the ping needs each error.
        try:
            return grade_day(bucket, day, cache=args.cache, out=args.out)
        except (Exception, SystemExit) as error:
            failures[day] = error
            raise

    try:
        result = backfill.run(
            backfill.days_between(f"{first:%Y%m%d}", f"{last:%Y%m%d}"),
            grade=grade,
            is_done=report_exists(bucket, args.out, upload=True),
            after_day=lambda day: backfill.prune_cache(args.cache, day),
        )
        code = backfill.exit_code(result)
        summary = ", ".join(f"{key} {len(days)}" for key, days in result.items())
        graded = args.cache / "graded" / arrivals.VERSION
        if not aggregate.fetch_arrivals(bucket(), graded, aggregate.reports_beside(graded)):
            # No day of this layout version has finished yet, as on a first
            # deploy or after a version bump. The day counts say more than the
            # error `aggregate` would raise over an empty directory.
            heartbeat(False, ping_body(f"no finished day to publish: {summary}", failures, result))
            return code or 1
        build_site(bucket, graded, cache=args.cache, out=args.out / "site")
        r2_problem = copy_to_r2(bucket, args.out / "site")
    except BaseException as error:
        heartbeat(False, f"daily run crashed: {redact(repr(error))}")
        raise

    if r2_problem:
        heartbeat(False, ping_body(f"{r2_problem}. {summary}", failures, result))
        return code or 1
    heartbeat(code == 0, ping_body(summary, failures, result))
    return code


def copy_to_r2(bucket: Bucket, site_dir: Path) -> str | None:
    """Copy the published run to R2 and check it from outside. Returns what went wrong, or None.

    A Notice carries its own wording. For any other error only the code and the
    call are kept, because botocore's messages hold the endpoint URL and the
    heartbeat is sent to a third party.
    """
    try:
        r2.copy_if_configured(bucket(), site_dir=site_dir)
    except r2.Notice as error:
        problem = str(error)
    except Exception as error:
        problem = (
            f"R2 copy failed: {r2.describe(error)}; the site is published to Cloud Storage only"
        )
    else:
        return None
    print(f"  {problem}")
    return problem


def run_publish_r2(args: argparse.Namespace) -> int:
    """Copy one run from the derived bucket to R2. Reads Cloud Storage only.

    It passes no site directory, so it neither probes nor reads R2_PUBLIC_URL. A
    Notice is printed as one line with exit status 1, not as a traceback.
    """
    try:
        copied = r2.copy_if_configured(Bucket()(), args.site_run)
    except r2.Notice as error:
        sys.exit(str(error))
    if not copied:
        sys.exit("nothing copied: set R2_ENDPOINT, R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY")
    return 0


def run_aggregate(args: argparse.Namespace) -> int:
    bucket = Bucket()
    # Before any download, so a refused run costs nothing.
    timetables = local_timetables(args.gtfs_dir, upload=not args.no_upload)
    if args.from_bucket and args.reports:
        # The fetch empties its reports folder, so it must not be one of yours.
        sys.exit("--reports is for local runs. --from-bucket downloads its own reports.")
    graded = args.arrivals or Path(f"out/arrivals/{arrivals.VERSION}")
    if args.from_bucket:
        # A directory of its own under the cache, because fetching empties it
        # first, and --arrivals may hold days graded locally and never uploaded.
        graded = args.cache / "graded" / arrivals.VERSION
        aggregate.fetch_arrivals(bucket(), graded, aggregate.reports_beside(graded))
    return build_site(
        bucket,
        graded,
        cache=args.cache,
        out=args.out,
        timetables=timetables,
        upload=not args.no_upload,
        reports=args.reports,
    )


def build_site(
    bucket: Bucket,
    arrivals_dir: Path,
    *,
    cache: Path,
    out: Path,
    timetables: dict[str, Path] | None = None,
    upload: bool = True,
    reports: Path | None = None,
) -> int:
    """Summarise every graded day into the site's JSON, and upload it.

    `reports` is where health.json reads the saved daily reports. It defaults to
    the folder beside the arrivals, which is where both `--from-bucket` and a
    local `arrivals` run leave them.
    """
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

    written, names = aggregate.build(
        con, catalogue, out, first, last, days, reports or aggregate.reports_beside(arrivals_dir)
    )
    biggest = max(written, key=lambda row: row[2])
    total = sum(row[1] for row in written)

    print(
        f"\n  wrote {len(written)} line files + index.json + status.json + network.json + health.json to {out}"
    )
    print(
        f"  {total / 1e6:.2f} MB total, largest is line {biggest[0]} at "
        f"{biggest[1] / 1e3:.0f} KB ({biggest[2] / 1e3:.0f} KB gzipped)"
    )
    if upload:
        count, where = aggregate.upload(bucket(), out, names)
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
        help="YYYY-MM-DD or YYYYMMDD. Defaults to the latest complete day, yesterday from 07:00 Pacific.",
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
    one.add_argument(
        "--allow-egress",
        action="store_true",
        help="download raw files from outside Google Cloud, which costs about $0.12 per GiB",
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

    publish = jobs.add_parser(
        "publish-r2",
        help="copy a published run from the derived bucket to R2",
    )
    publish.add_argument(
        "--run",
        dest="site_run",
        metavar="RUN",
        help=f"the run to copy. Defaults to the run named by {aggregate.POINTER}.",
    )
    publish.set_defaults(run=run_publish_r2)

    many = jobs.add_parser(
        "backfill", parents=[shared], help="grade every day in a range not already done"
    )
    many.add_argument("--from", dest="first", required=True, help="first service day, YYYY-MM-DD")
    many.add_argument(
        "--to",
        dest="last",
        default=yesterday(),
        help="last service day. Defaults to the latest complete day, yesterday from 07:00 Pacific.",
    )
    many.add_argument("--out", type=Path, default=Path("out"), help="where the Parquet goes")
    many.add_argument(
        "--no-upload",
        action="store_true",
        help="write locally; a day counts as done when its report is on local disk",
    )
    many.add_argument(
        "--allow-egress",
        action="store_true",
        help="download raw files from outside Google Cloud, which costs about $0.12 per GiB",
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
    every.add_argument(
        "--reports",
        type=Path,
        help=(
            "the saved daily reports health.json reads, one service_date=DAY/report.json each "
            f"(default: reports/{arrivals.VERSION} beside the arrivals folder's parent)"
        ),
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
