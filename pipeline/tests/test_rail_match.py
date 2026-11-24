"""The rail matcher on the hand-built day of fixture_rail.py. Expected values are in its docstring."""

import pytest
from fixture_rail import RAIL, run_rail_day

from howlate_pipeline import railmatch, report


@pytest.fixture
def con(tmp_path):
    return run_rail_day(tmp_path)


def delays(con, trip):
    return con.execute(
        "SELECT delay_seconds, source FROM arrivals WHERE agency = ? AND trip_id = ? "
        "ORDER BY stop_sequence",
        [RAIL, trip],
    ).fetchall()


def test_a_good_id_is_kept_and_graded_as_before(con):
    assert delays(con, "R1") == [
        (30, "origin_departure"),
        (30, "stopped_at"),
        (30, "stopped_at"),
        (30, "stopped_at"),
        (30, "stopped_at"),
        (30, "stopped_at"),
        (90, "approach"),
    ]


def test_a_stale_id_is_matched_to_the_trip_the_vehicle_ran(con):
    assert delays(con, "R2") == [(60, "matched")] * 6 + [(120, "matched")]


def test_a_later_start_id_is_matched_to_the_trip_the_vehicle_ran(con):
    assert delays(con, "R3") == [(90, "matched")] * 6 + [(150, "matched")]
    assert delays(con, "L1") == []


def test_a_run_that_is_not_confident_is_left_ungraded(con):
    vehicles = con.execute("SELECT DISTINCT vehicle_id FROM arrivals WHERE agency = ?", [RAIL])
    assert sorted(v for (v,) in vehicles.fetchall() if v) == ["V1", "V2", "V3"]
    assert con.execute("SELECT count(*) FROM observations WHERE vehicle_id = 'V4'").fetchone() == (
        0,
    )


def test_the_report_counts_each_outcome_for_the_line(con):
    assert report.rail_matching(con) == [("801", 1, 2, 1)]
    assert report.document(con, "20260818")["rail_matching"] == [
        {"line": "801", "trusted": 1, "matched": 2, "ungraded": 1}
    ]


def test_the_rail_check_judges_the_trip_the_grader_used(con, tmp_path, monkeypatch):
    assert report.rail_misfits(con) == [("801", 3, 0)]
    monkeypatch.setattr(railmatch, "ENABLED", False)
    off = run_rail_day(tmp_path / "off")
    assert report.rail_misfits(off) == [("801", 3, 1)]


def test_a_bus_day_is_graded_the_same_with_the_matcher_on_or_off(con, tmp_path, monkeypatch):
    query = (
        "SELECT trip_id, stop_sequence, stop_id, delay_seconds, source, vehicle_id, is_origin "
        "FROM arrivals WHERE agency = 'LACMTA' ORDER BY trip_id, stop_sequence"
    )
    monkeypatch.setattr(railmatch, "ENABLED", False)
    off = run_rail_day(tmp_path / "off")
    assert con.execute(query).fetchall() == off.execute(query).fetchall()
    assert con.execute(query).fetchall()


def test_the_matcher_off_grades_every_rail_run_on_its_reported_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(railmatch, "ENABLED", False)
    con = run_rail_day(tmp_path)
    assert {delay for delay, _ in delays(con, "R3")} == {None}
    assert {source for _, source in delays(con, "R1")} == {
        "origin_departure",
        "stopped_at",
        "approach",
    }
    assert report.rail_matching(con) == []
