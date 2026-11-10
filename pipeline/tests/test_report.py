"""The report runs on the fixture day and adds up to the fixture's own numbers.

Mostly a guard on the library: report.py is where the pipeline pulls single
rows out of DuckDB, which is the first thing a DuckDB upgrade broke.
"""

import pytest
from fixture_day import SERVICE_DATE, run_day

from howlate_pipeline import report


@pytest.fixture(scope="module")
def con(tmp_path_factory):
    return run_day(tmp_path_factory.mktemp("day"))


def test_summarise_counts_the_fixture_day(con):
    stats = report.summarise(con)
    assert stats["scheduled_stops"] == 8
    # T1's last stop and both of T3's were never seen. The rest: 2 origin
    # departures, 2 stopped_at, 1 approach.
    assert stats["measured"] == 5
    assert stats["stopped"] == 2
    assert stats["approached"] == 1
    assert stats["trips"] == 3


def test_show_runs_to_the_end(con, capsys):
    # The fixture is far too small for the real ranges, so this checks only
    # that every line of the report prints, not that it passes.
    report.show(con, SERVICE_DATE)
    assert "lines scheduled today but never seen" in capsys.readouterr().out
