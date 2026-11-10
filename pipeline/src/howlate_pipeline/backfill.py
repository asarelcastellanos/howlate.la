"""Grade a range of service days, once each, picking up where it stopped.

    python -m howlate_pipeline backfill --from 2026-08-18 --to 2026-11-07

Built for the first run over the whole archive, 82 days, and for catching up
after the daily job misses some. A day counts as done when its report is in the
bucket. The report is uploaded after both tables, and a regrade deletes the old
report before touching anything else, so a run that is killed partway, by a
Spot VM being reclaimed or by Ctrl-C, grades again only the day it was in.

`--regrade-before TIME` grades days again whose report was written before
TIME. A day regraded after TIME counts as done, so an interrupted regrade,
restarted with the same TIME, resumes rather than starting over. A time rather
than a version, because every commit before a release carries the same
version string, and a fix made between two of them must still be able to
regrade.

One day failing does not stop the rest. A day whose checks fail is still
written, as `arrivals` does on its own. A day that raises, or whose done check
raises, is listed at the end and left for the next run. A cleanup that fails
after a day was graded is reported on its own, and the day keeps its result.
"""

import shutil
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path


def days_between(first: str, last: str) -> list[str]:
    """Every service date from first to last, inclusive, as YYYYMMDD."""
    start = datetime.strptime(first.replace("-", ""), "%Y%m%d")
    end = datetime.strptime(last.replace("-", ""), "%Y%m%d")
    if end < start:
        raise SystemExit(f"--to {last} is before --from {first}")
    return [(start + timedelta(days=n)).strftime("%Y%m%d") for n in range((end - start).days + 1)]


def prune_cache(cache: Path, service_date: str) -> None:
    """Drop the raw partition no later day in the run will read.

    Day D reads the UTC partitions D-1, D and D+1, so once D is graded every
    partition before D is finished with, as long as days run in order. Without
    this a full backfill keeps every raw file it downloaded, over 100 GB, on a
    disk sized for a few days. Everything older goes, not only D-1, so days
    skipped as done, and ranges run one after another in date order, cannot
    strand partitions. A range run before an earlier one leaves its last few
    partitions until a later day is graded.
    """
    keep_from = f"dt={datetime.strptime(service_date, '%Y%m%d'):%Y-%m-%d}"
    root = cache / "vehicle_positions"
    if not root.exists():
        return
    for partition in root.iterdir():
        # dt=YYYY-MM-DD names sort in date order.
        if partition.name.startswith("dt=") and partition.name < keep_from:
            shutil.rmtree(partition, ignore_errors=True)


def done_check(
    report_time: Callable[[str], datetime | None], regrade_before: datetime | None
) -> Callable[[str], bool]:
    """Whether a day is done, from when its saved report was written.

    `report_time` returns that moment, or None when there is no report. With
    `regrade_before`, a report written before it does not count.
    """

    def is_done(day: str) -> bool:
        written = report_time(day)
        if written is None:
            return False
        return regrade_before is None or written >= regrade_before

    return is_done


def run(
    days: list[str],
    grade: Callable[[str], int],
    is_done: Callable[[str], bool],
    after_day: Callable[[str], None],
    log: Callable[[str], None] = print,
) -> dict[str, list[str]]:
    """Grade each day not already done, in order, and say what happened.

    `grade` returns the day's exit code: 0 when every check passed, 2 when a
    check failed but the day was written. Anything it raises marks the day as
    an error and the run moves on.
    """
    result: dict[str, list[str]] = {
        "skipped": [], "passed": [], "checks_failed": [], "errors": [], "cleanup_failed": [],
    }  # fmt: skip
    for day in days:
        try:
            if is_done(day):
                result["skipped"].append(day)
                continue
            log(f"=== {day}")
            code = grade(day)
        except (Exception, SystemExit) as error:  # noqa: BLE001 - one day must not stop the rest
            log(f"  {day} failed: {error!r}")
            result["errors"].append(day)
            continue
        # The day is graded and saved, so its result stands whatever cleanup
        # does next.
        result["passed" if code == 0 else "checks_failed"].append(day)
        try:
            after_day(day)
        except Exception as error:  # noqa: BLE001 - a full disk later is better than a lost day
            log(f"  {day} cleanup failed: {error!r}")
            result["cleanup_failed"].append(day)

    log(
        f"\n  {len(result['passed'])} passed, {len(result['checks_failed'])} with failed "
        f"checks, {len(result['errors'])} errors, {len(result['skipped'])} already done"
    )
    for key in ("checks_failed", "errors", "cleanup_failed"):
        if result[key]:
            log(f"  {key.replace('_', ' ')}: {', '.join(result[key])}")
    return result


def exit_code(result: dict[str, list[str]]) -> int:
    """1 if any day or cleanup errored, 2 if any day's checks failed, otherwise 0."""
    if result["errors"] or result["cleanup_failed"]:
        return 1
    return 2 if result["checks_failed"] else 0
