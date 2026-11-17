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


def test_the_default_day_is_two_days_before_the_pacific_day():
    assert cli.yesterday(pacific(2026, 11, 16, 17, 0)) == "20261114"
    assert cli.yesterday(pacific(2026, 11, 16, 5, 0)) == "20261114"
    assert cli.yesterday(pacific(2026, 11, 16, 23, 59)) == "20261114"


def test_the_default_day_counts_calendar_days_across_daylight_saving():
    assert cli.yesterday(pacific(2026, 3, 9, 17, 0)) == "20260307"
    assert cli.yesterday(pacific(2026, 11, 2, 17, 0)) == "20261031"


def test_with_no_clock_given_the_helper_reads_the_utc_clock(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return pacific(2026, 11, 16, 17, 0).astimezone(tz) if tz else cls(2026, 11, 17, 1, 0)

    monkeypatch.setattr(howlate_pipeline, "datetime", Clock)
    assert pacific_today() == date(2026, 11, 16)
