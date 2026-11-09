"""The report runs on the fixture day and adds up to the fixture's own numbers.

Mostly a guard on the library: report.py is where the pipeline pulls single
rows out of DuckDB, which is the first thing a DuckDB upgrade broke.
"""

import pytest
from fixture_day import SERVICE_DATE, build_raw, build_timetable

from howlate_pipeline import arrivals, report


@pytest.fixture(scope="module")
def con(tmp_path_factory):
    root = tmp_path_factory.mktemp("day")
    con = arrivals.connect()
    files = arrivals.local_files(build_raw(root / "raw"), SERVICE_DATE)
    arrivals.load_observations(con, files, SERVICE_DATE)
    arrivals.load_schedule(con, {"LACMTA": build_timetable(root / "gtfs_bus")}, SERVICE_DATE)
    arrivals.match(con, SERVICE_DATE)
    return con


def test_summarise_counts_the_fixture_day(con):
    stats = report.summarise(con)
    assert stats["scheduled_stops"] == 6
    # Every stop but T1's last: 2 origin departures, 2 stopped_at, 1 approach.
    assert stats["measured"] == 5
    assert stats["stopped"] == 2
    assert stats["approached"] == 1
    assert stats["trips"] == 2


def test_show_runs_to_the_end(con, capsys):
    # The fixture is far too small for the real ranges, so this checks only
    # that every line of the report prints, not that it passes.
    report.show(con, SERVICE_DATE)
    assert "lines scheduled today but never seen" in capsys.readouterr().out
