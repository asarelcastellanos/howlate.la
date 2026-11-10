"""The backfill's promises: each day once, resumable, and one bad day stops nothing.

`grade`, `is_done` and `after_day` are fakes here. A day becomes done when its
fake grade finishes, the way a report landing in the bucket does for real.
"""

from datetime import UTC, datetime, timedelta

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


def test_cleanup_runs_after_each_day_that_was_graded():
    archive = Archive(done=["20260818"], raises={"20260819": RuntimeError("boom")})
    archive.run()
    # Not after the 19th, which raised: a retry needs its raw files again.
    assert archive.finished == ["20260820", "20260821"]


def test_pruning_drops_only_the_partition_no_later_day_reads(tmp_path):
    for day in ["2026-08-17", "2026-08-18", "2026-08-19"]:
        (tmp_path / "vehicle_positions" / f"dt={day}").mkdir(parents=True)
    (tmp_path / "gtfs").mkdir()

    backfill.prune_cache(tmp_path, "20260818")

    left = sorted(p.name for p in (tmp_path / "vehicle_positions").iterdir())
    # The 19th still needs the 18th and 19th partitions.
    assert left == ["dt=2026-08-18", "dt=2026-08-19"]
    assert (tmp_path / "gtfs").exists()


def test_pruning_drops_every_older_partition_left_behind(tmp_path):
    # A run that skipped done days, or an earlier separate run, can leave
    # older partitions. All of them go once a later day is graded.
    for day in ["2026-08-10", "2026-08-12", "2026-08-17", "2026-08-18", "2026-08-19"]:
        (tmp_path / "vehicle_positions" / f"dt={day}").mkdir(parents=True)
    backfill.prune_cache(tmp_path, "20260818")
    left = sorted(p.name for p in (tmp_path / "vehicle_positions").iterdir())
    assert left == ["dt=2026-08-18", "dt=2026-08-19"]


def test_pruning_an_empty_cache_is_harmless(tmp_path):
    backfill.prune_cache(tmp_path, "20260818")


def test_a_failing_done_check_does_not_stop_the_rest():
    archive = Archive()

    def flaky(day):
        if day == "20260819":
            raise ConnectionError("bucket unreachable")
        return archive.is_done(day)

    result = backfill.run(DAYS, archive.grade, flaky, archive.after_day, log=lambda _: None)
    assert result["errors"] == ["20260819"]
    assert archive.graded == ["20260818", "20260820", "20260821"]


def test_a_failing_cleanup_keeps_the_days_result_and_does_not_stop_the_rest():
    archive = Archive(codes={"20260819": 2})

    def cleanup(day):
        if day == "20260819":
            raise OSError("disk")

    result = backfill.run(DAYS, archive.grade, archive.is_done, cleanup, log=lambda _: None)
    # The 19th was graded and saved; its failed checks are still reported, and
    # the cleanup failure is reported on its own.
    assert result["checks_failed"] == ["20260819"]
    assert result["cleanup_failed"] == ["20260819"]
    assert result["errors"] == []
    assert archive.graded == DAYS
    assert backfill.exit_code(result) == 1


def test_an_interrupt_during_a_grade_is_not_swallowed_by_cleanup():
    archive = Archive(raises={"20260819": KeyboardInterrupt()})

    def cleanup(day):
        raise OSError("disk")

    with pytest.raises(KeyboardInterrupt):
        backfill.run(DAYS, archive.grade, archive.is_done, cleanup, log=lambda _: None)


NOV_10 = datetime(2026, 11, 10, 8, tzinfo=UTC)


def at(hours_after: int) -> datetime:
    return NOV_10 + timedelta(hours=hours_after)


def test_a_day_with_a_report_is_done():
    is_done = backfill.done_check({"20260818": at(-48)}.get, None)
    assert is_done("20260818") is True
    assert is_done("20260819") is False


def test_regrade_redoes_only_days_reported_before_the_cutoff():
    written = {"20260818": at(-48), "20260819": at(+1)}
    is_done = backfill.done_check(written.get, NOV_10)
    # The 19th was regraded after the cutoff: restarted with the same cutoff,
    # an interrupted regrade resumes from there instead of starting over.
    assert is_done("20260818") is False
    assert is_done("20260819") is True
    assert is_done("20260820") is False


def test_a_day_not_yet_complete_is_refused_before_anything_runs(monkeypatch):
    import argparse

    from howlate_pipeline import __main__ as cli

    monkeypatch.setattr(cli, "yesterday", lambda: "20261107")
    # Refused before any client is made, so no credentials are needed here.
    monkeypatch.setattr(cli.storage, "Client", lambda: pytest.fail("made a client"))
    args = argparse.Namespace(last="2026-11-08", first="2026-11-01", regrade_before=None)
    with pytest.raises(SystemExit):
        cli.run_backfill(args)
    # An unpadded date is a date, not a string that sorts after November.
    args.last = "2026-1-9"
    monkeypatch.setattr(cli, "grade_day", lambda *a, **k: pytest.fail("graded"))
    monkeypatch.setattr(
        cli.storage, "Client", lambda: (_ for _ in ()).throw(RuntimeError("client"))
    )
    with pytest.raises(RuntimeError, match="client"):
        cli.run_backfill(args)


def test_arrivals_refuses_an_incomplete_day_too(monkeypatch):
    import argparse

    from howlate_pipeline import __main__ as cli

    monkeypatch.setattr(cli, "yesterday", lambda: "20261107")
    monkeypatch.setattr(cli, "grade_day", lambda *a, **k: pytest.fail("graded"))
    with pytest.raises(SystemExit):
        cli.run_arrivals(argparse.Namespace(service_date="2026-11-08"))
