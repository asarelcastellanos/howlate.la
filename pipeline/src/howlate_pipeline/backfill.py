"""Grade a range of service days, once each, picking up where it stopped.

    python -m howlate_pipeline backfill --from 2026-08-18 --to 2026-11-07

Built for the first run over the whole archive, 82 days, and for catching up
after the daily job misses some. The rules, each one tested:

Dates
    A day is written YYYY-MM-DD or YYYYMMDD and nothing looser. "2026-1-12"
    is refused rather than read as some other day.

Done
    A day is done when its report exists, in the bucket or, with
    --no-upload, on disk. Nothing else is consulted. The report is uploaded
    after both tables, and a grade deletes the old report before touching
    anything else, so with one writer per day a run killed partway, by a Spot
    VM being reclaimed or by Ctrl-C, grades again only the day it was in.

Outcomes
    Each day not done is graded. A day whose checks fail is still written,
    as `arrivals` does on its own. A day whose grade or done check raises is
    listed under errors and left for the next run. Ctrl-C stops the run.

Cache
    After every day attempted, whatever the outcome, raw partitions older
    than that day are deleted. A failed day's retry downloads up to three
    partitions again (the day and the day either side); in exchange the
    cache stays at a few days, even when every day fails. A cleanup that
    cannot delete a partition is reported on its own and does not change the
    day's result.

To grade a done day again, delete its report and run the backfill over it:

    gcloud storage rm gs://howlate-derived/reports/v2/service_date=2026-08-18/report.json
"""

import re
import shutil
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

# ASCII digits only: \d alone would also accept other scripts' digits.
DAY = re.compile(r"([0-9]{4})-([0-9]{2})-([0-9]{2})|([0-9]{4})([0-9]{2})([0-9]{2})")


def parse_day(text: str) -> datetime:
    """A service day from YYYY-MM-DD or YYYYMMDD, and nothing looser."""
    match = DAY.fullmatch(text)
    if not match:
        raise SystemExit(f"{text!r} is not a day; write it as YYYY-MM-DD")
    try:
        return datetime(*(int(part) for part in match.groups() if part is not None))
    except ValueError:
        raise SystemExit(f"{text!r} is not a real date") from None


def days_between(first: str, last: str) -> list[str]:
    """Every service date from first to last, inclusive, as YYYYMMDD."""
    start, end = parse_day(first), parse_day(last)
    if end < start:
        raise SystemExit(f"--to {last} is before --from {first}")
    return [(start + timedelta(days=n)).strftime("%Y%m%d") for n in range((end - start).days + 1)]


def prune_cache(cache: Path, service_date: str) -> None:
    """Delete every raw partition older than this day.

    Day D reads the UTC partitions D-1, D and D+1. Days run in order, so once
    D has been attempted no later day in the run reads anything before D.
    """
    root = cache / "vehicle_positions"
    if not root.exists():
        return
    keep_from = f"dt={parse_day(service_date):%Y-%m-%d}"
    for partition in root.iterdir():
        # dt=YYYY-MM-DD names sort in date order.
        if partition.name.startswith("dt=") and partition.name < keep_from:
            # Not ignore_errors: a partition that cannot be deleted is a
            # gigabyte left on a small disk, and the run should say so.
            shutil.rmtree(partition)


def run(
    days: list[str],
    grade: Callable[[str], int],
    is_done: Callable[[str], bool],
    after_day: Callable[[str], None],
    log: Callable[[str], None] = print,
) -> dict[str, list[str]]:
    """Grade each day not already done, in order, and say what happened.

    `grade` returns the day's exit code: 0 when every check passed, 2 when a
    check failed but the day was written.
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
        else:
            result["passed" if code == 0 else "checks_failed"].append(day)

        # Every attempted day, graded or failed, so failures cannot fill the disk.
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
