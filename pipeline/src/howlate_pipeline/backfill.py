"""Grade a range of service days, once each, picking up where it stopped.

    python -m howlate_pipeline backfill --from 2026-08-18 --to 2026-11-07

Built for the first run over the whole archive, 82 days, and for catching up
after the daily job misses some. A day counts as done when its report is in the
bucket. The report is uploaded after both tables, and a regrade deletes the old
report before touching anything else, so a run that is killed partway, by a
Spot VM being reclaimed or by Ctrl-C, grades again only the day it was in.

`--regrade` grades days again that an older pipeline version graded. A day this
version already regraded counts as done, so an interrupted regrade resumes
rather than starting over.

One day failing does not stop the rest. A day whose checks fail is still
written, as `arrivals` does on its own, and a day that raises, or whose done
check or cleanup raises, is listed at the end and left for the next run.
"""

import json
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
    skipped as done or ranges run separately cannot strand partitions.
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
    read_report: Callable[[str], str | None], regrade: bool, version: str
) -> Callable[[str], bool]:
    """Whether a day is done, from its saved report.

    `read_report` returns the report's text, or None when there is none. With
    `regrade`, a day counts as done only if `version` wrote its report, so an
    interrupted regrade resumes instead of starting over.
    """

    def is_done(day: str) -> bool:
        text = read_report(day)
        if text is None:
            return False
        return not regrade or json.loads(text).get("pipeline_version") == version

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
    result: dict[str, list[str]] = {"skipped": [], "passed": [], "checks_failed": [], "errors": []}
    for day in days:
        try:
            if is_done(day):
                result["skipped"].append(day)
                continue
            log(f"=== {day}")
            try:
                code = grade(day)
            finally:
                # Cleanup runs for a failed day too, before the error is noted.
                after_day(day)
        except (Exception, SystemExit) as error:  # noqa: BLE001 - one day must not stop the rest
            log(f"  {day} failed: {error!r}")
            result["errors"].append(day)
        else:
            result["passed" if code == 0 else "checks_failed"].append(day)

    log(
        f"\n  {len(result['passed'])} passed, {len(result['checks_failed'])} with failed "
        f"checks, {len(result['errors'])} errors, {len(result['skipped'])} already done"
    )
    for key in ("checks_failed", "errors"):
        if result[key]:
            log(f"  {key.replace('_', ' ')}: {', '.join(result[key])}")
    return result


def exit_code(result: dict[str, list[str]]) -> int:
    """1 if any day errored, 2 if any day's checks failed, otherwise 0."""
    if result["errors"]:
        return 1
    return 2 if result["checks_failed"] else 0
