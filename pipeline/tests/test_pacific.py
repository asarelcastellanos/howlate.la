"""The Pacific calendar day, which the default grading day is counted from.

Cloud Run's clock is UTC. From 16:00 Pacific onward (17:00 when daylight saving
is over) the UTC date is already tomorrow, so a run started then must not read it.
"""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

import howlate_pipeline
from howlate_pipeline import ZONE, pacific_today
from howlate_pipeline import __main__ as cli


def pacific(*when: int) -> datetime:
    """A Pacific wall time, handed over as the UTC instant the machine would see."""
    return datetime(*when, tzinfo=ZoneInfo(ZONE)).astimezone(UTC)


# Each row is a Pacific wall time, the Pacific date, and the date a UTC clock would read.
@pytest.mark.parametrize(
    ("now", "day", "utc_day"),
    [
        (pacific(2026, 11, 16, 17, 0), date(2026, 11, 16), date(2026, 11, 17)),
        (pacific(2026, 11, 16, 5, 0), date(2026, 11, 16), date(2026, 11, 16)),
        (pacific(2026, 11, 16, 23, 59), date(2026, 11, 16), date(2026, 11, 17)),
        # Daylight saving starts 2026-03-08, so 17:00 is 00:00 UTC after it and 01:00 before.
        (pacific(2026, 3, 8, 17, 0), date(2026, 3, 8), date(2026, 3, 9)),
        (pacific(2026, 3, 7, 17, 0), date(2026, 3, 7), date(2026, 3, 8)),
        # It ends 2026-11-01, when 23:59 Pacific is 07:59 UTC the next day.
        (pacific(2026, 11, 1, 23, 59), date(2026, 11, 1), date(2026, 11, 2)),
        (pacific(2026, 11, 1, 0, 30), date(2026, 11, 1), date(2026, 11, 1)),
    ],
)
def test_pacific_today_follows_the_pacific_calendar(now, day, utc_day):
    assert now.date() == utc_day
    assert pacific_today(now) == day


def test_the_default_day_is_one_day_before_the_pacific_day_from_07_00():
    # The scheduled run is at 08:00. Grading at 05:00 missed bus arrivals, because
    # the timetable runs buses until 05:45 and the last report came at 06:12.
    assert cli.yesterday(pacific(2026, 11, 16, 8, 0)) == "20261115"
    assert cli.yesterday(pacific(2026, 11, 16, 7, 0)) == "20261115"
    assert cli.yesterday(pacific(2026, 11, 16, 17, 0)) == "20261115"
    assert cli.yesterday(pacific(2026, 11, 16, 23, 59)) == "20261115"


def test_before_07_00_the_default_day_is_two_days_back_because_yesterday_is_still_running():
    assert cli.yesterday(pacific(2026, 11, 16, 6, 59)) == "20261114"
    assert cli.yesterday(pacific(2026, 11, 16, 5, 0)) == "20261114"
    assert cli.yesterday(pacific(2026, 11, 16, 0, 0)) == "20261114"


def test_the_default_day_counts_calendar_days_across_daylight_saving():
    assert cli.yesterday(pacific(2026, 3, 9, 17, 0)) == "20260308"
    assert cli.yesterday(pacific(2026, 11, 2, 17, 0)) == "20261101"
    # 07:00 is local time on the days the clocks change, not seven elapsed hours.
    assert cli.yesterday(pacific(2026, 3, 8, 7, 0)) == "20260307"
    assert cli.yesterday(pacific(2026, 3, 8, 6, 59)) == "20260306"
    assert cli.yesterday(pacific(2026, 11, 1, 7, 0)) == "20261031"
    assert cli.yesterday(pacific(2026, 11, 1, 6, 59)) == "20261030"


def test_with_no_clock_given_the_helper_reads_the_utc_clock(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return pacific(2026, 11, 16, 17, 0).astimezone(tz) if tz else cls(2026, 11, 17, 1, 0)

    monkeypatch.setattr(howlate_pipeline, "datetime", Clock)
    assert pacific_today() == date(2026, 11, 16)


@pytest.fixture
def latest_complete_day_is_nov_7(monkeypatch):
    """The latest complete day is 2026-11-07, as at 09:00 Pacific on 2026-11-08."""
    monkeypatch.setattr(cli, "yesterday", lambda now=None: "20261107")


@pytest.mark.parametrize("text", ["2026-11-07", "20261107", "2026-11-06"])
def test_the_latest_complete_day_and_earlier_days_are_accepted(latest_complete_day_is_nov_7, text):
    # The latest day is the one the default grades, so it must be allowed.
    assert cli.require_complete(text) == text.replace("-", "")


@pytest.mark.parametrize("text", ["2026-11-08", "20261109", "2026-11-10"])
def test_a_day_after_the_latest_complete_one_is_refused_with_that_day_named(
    latest_complete_day_is_nov_7, text
):
    with pytest.raises(SystemExit, match="is not complete yet; the latest is 2026-11-07"):
        cli.require_complete(text)
