"""The backfill's promises: each day once, resumable, and one bad day stops nothing.

`grade`, `is_done` and `after_day` are fakes here. A day becomes done when its
fake grade finishes, the way a report landing in the bucket does for real.
"""

import pytest

from howlate_pipeline import backfill

DAYS = ["20260818", "20260819", "20260820", "20260821"]


class Archive:
    """Which days are done, and every call made, in order."""

    def __init__(self, done=(), codes=None, raises=None):
        self.done = set(done)
        self.codes = codes or {}
        self.raises = raises or {}
        self.graded: list[str] = []
        self.finished: list[str] = []

    def grade(self, day: str) -> int:
        self.graded.append(day)
        if day in self.raises:
            raise self.raises[day]
        self.done.add(day)
        return self.codes.get(day, 0)

    def is_done(self, day: str) -> bool:
        return day in self.done

    def after_day(self, day: str) -> None:
        self.finished.append(day)

    def run(self):
        return backfill.run(DAYS, self.grade, self.is_done, self.after_day, log=lambda _: None)


def test_days_between_is_inclusive_and_crosses_months():
    assert backfill.days_between("2026-08-30", "2026-09-02") == [
        "20260830", "20260831", "20260901", "20260902",
    ]  # fmt: skip
    assert backfill.days_between("20260818", "20260818") == ["20260818"]


def test_a_reversed_range_is_refused():
    with pytest.raises(SystemExit):
        backfill.days_between("2026-09-02", "2026-08-30")


def test_every_day_is_graded_once_in_order():
    archive = Archive()
    result = archive.run()
    assert archive.graded == DAYS
    assert result["passed"] == DAYS
    assert backfill.exit_code(result) == 0


def test_days_already_done_are_skipped():
    archive = Archive(done=["20260818", "20260820"])
    result = archive.run()
    assert archive.graded == ["20260819", "20260821"]
    assert result["skipped"] == ["20260818", "20260820"]


def test_a_killed_run_resumes_at_the_day_it_was_in():
    # Killed while grading the 20th, as a reclaimed Spot VM would be.
    archive = Archive(raises={"20260820": KeyboardInterrupt()})
    with pytest.raises(KeyboardInterrupt):
        archive.run()
    assert archive.graded == ["20260818", "20260819", "20260820"]

    del archive.raises["20260820"]
    archive.graded.clear()
    archive.run()
    # Only the interrupted day and the ones after it run again.
    assert archive.graded == ["20260820", "20260821"]


def test_an_error_on_one_day_does_not_stop_the_rest():
    archive = Archive(raises={"20260819": RuntimeError("no raw files")})
    result = archive.run()
    assert archive.graded == DAYS
    assert result["errors"] == ["20260819"]
    assert "20260819" not in archive.done  # left for the next run
    assert backfill.exit_code(result) == 1


def test_a_systemexit_from_a_day_is_caught_too():
    # gtfs.prepare raises SystemExit when no timetable covers a day.
    archive = Archive(raises={"20260819": SystemExit("no timetable")})
    result = archive.run()
    assert result["errors"] == ["20260819"]
    assert archive.graded == DAYS


def test_failed_checks_are_written_and_reported():
    archive = Archive(codes={"20260820": 2})
    result = archive.run()
    assert result["checks_failed"] == ["20260820"]
    assert "20260820" in archive.done
    assert backfill.exit_code(result) == 2


def test_cleanup_runs_after_every_graded_day_including_failures():
    archive = Archive(done=["20260818"], raises={"20260819": RuntimeError("boom")})
    archive.run()
    assert archive.finished == ["20260819", "20260820", "20260821"]


def test_pruning_drops_only_the_partition_no_later_day_reads(tmp_path):
    for day in ["2026-08-17", "2026-08-18", "2026-08-19"]:
        (tmp_path / "vehicle_positions" / f"dt={day}").mkdir(parents=True)
    (tmp_path / "gtfs").mkdir()

    backfill.prune_cache(tmp_path, "20260818")

    left = sorted(p.name for p in (tmp_path / "vehicle_positions").iterdir())
    # The 19th still needs the 18th and 19th partitions.
    assert left == ["dt=2026-08-18", "dt=2026-08-19"]
    assert (tmp_path / "gtfs").exists()
