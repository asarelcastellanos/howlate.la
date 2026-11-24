"""The rail matcher on the hand-built day of fixture_rail.py. Expected values are in its docstring."""

import pytest
from fixture_rail import RAIL, run_rail_day

from howlate_pipeline import railmatch, report


@pytest.fixture(autouse=True)
def matcher_on(monkeypatch):
    monkeypatch.setattr(railmatch, "ENABLED", True)


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
    assert sorted(v for (v,) in vehicles.fetchall() if v) == ["V1", "V2", "V3", "V5", "V6"]
    assert con.execute("SELECT count(*) FROM observations WHERE vehicle_id = 'V4'").fetchone() == (
        0,
    )


def test_the_report_counts_each_outcome_for_the_line(con):
    assert report.rail_matching(con) == [("801", 1, 3, 1), ("802", 0, 1, 0)]
    assert report.document(con, "20260818")["rail_matching"] == [
        {"line": "801", "trusted": 1, "matched": 3, "ungraded": 1},
        {"line": "802", "trusted": 0, "matched": 1, "ungraded": 0},
    ]


def test_the_rail_check_judges_the_trip_the_grader_used(con, tmp_path, monkeypatch):
    assert report.rail_misfits(con) == [("801", 4, 0), ("802", 1, 0)]
    monkeypatch.setattr(railmatch, "ENABLED", False)
    off = run_rail_day(tmp_path / "off")
    assert report.rail_misfits(off) == [("801", 4, 2)]


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


def test_a_run_on_shared_track_is_assigned_by_the_reported_route(con):
    assert delays(con, "X1") == [(30, "matched")] * 6 + [(90, "matched")]
    assert delays(con, "R2") == [(60, "matched")] * 6 + [(120, "matched")]


def test_a_run_with_no_reported_route_keeps_the_first_route_on_a_tie(tmp_path):
    from fixture_rail import build_rail_raw, build_rail_timetable

    from howlate_pipeline import arrivals, gtfs

    build_rail_raw(tmp_path / "raw")
    directory = build_rail_timetable(tmp_path / "gtfs_rail")
    trips, coords, _ = railmatch.load_timetable([directory], "20260818")
    routes = railmatch.build_routes(trips, coords)
    con = arrivals.connect()
    arrivals.load_observations(con, arrivals.local_files(tmp_path / "raw", "20260818"), "20260818")
    rows = con.execute(
        "SELECT DISTINCT vehicle_id, ts, lat, lon, trip_id, start_time, route_id FROM observations "
        "WHERE vehicle_id = 'V5' ORDER BY ts"
    ).fetchall()
    base = int(gtfs.day_base("20260818"))
    (with_route,) = railmatch.decide(rows, trips, routes, base)["V5"]
    blind = [row[:6] + (None,) for row in rows]
    (without,) = railmatch.decide(blind, trips, routes, base)["V5"]
    assert (with_route.run["route"], with_route.fit["best"].trip_id) == ("802", "X1")
    assert (without.run["route"], without.fit["best"].trip_id) == ("801", "R2")


def test_a_run_that_looks_trusted_and_is_a_misfit_is_matched(con):
    assert delays(con, "R4") == [(45, "matched")] * 6 + [(105, "matched")]
    row = con.execute(
        "SELECT reported_trip, trip_id, outcome FROM rail_runs WHERE vehicle_id = 'V6'"
    ).fetchone()
    assert row == ("R1", "R4", "matched")


@pytest.fixture
def graded(tmp_path, monkeypatch):
    import json

    from fixture_day import REPORTS, SERVICE_DATE, build_raw, build_timetable
    from fixture_rail import build_rail_raw, build_rail_timetable

    from howlate_pipeline import BUS_AGENCY
    from howlate_pipeline import __main__ as cli

    raw = build_raw(tmp_path / "raw", REPORTS)
    build_rail_raw(raw)
    timetables = {
        BUS_AGENCY: build_timetable(tmp_path / "gtfs_bus"),
        RAIL: build_rail_timetable(tmp_path / "gtfs_rail"),
    }
    monkeypatch.setattr(report, "MIN_LINE_RUNS", 1)
    real_checks = report.checks

    def only_rail_fails(con, s):
        return [
            c | {"ok": True} if c["name"] != "rail_misfit_pct" else c for c in real_checks(con, s)
        ]

    monkeypatch.setattr(report, "checks", only_rail_fails)

    def grade(*, other_check_fails=False):
        if other_check_fails:
            monkeypatch.setattr(
                report,
                "checks",
                lambda con, s: [
                    c | {"ok": False} if c["name"] == "feeds" else c
                    for c in only_rail_fails(con, s)
                ],
            )
        code = cli.grade_day(
            lambda: pytest.fail("made a client"),
            SERVICE_DATE,
            cache=tmp_path / "cache",
            out=tmp_path / "out",
            raw_dir=raw,
            timetables=timetables,
            upload=False,
        )
        saved = json.loads((tmp_path / "out" / cli.report_path(SERVICE_DATE)).read_text())
        return code, saved

    return grade


def rail_check(saved):
    return next(c for c in saved["checks"] if c["name"] == "rail_misfit_pct")


def test_a_failing_rail_check_is_advisory_while_the_matcher_is_off(graded, monkeypatch, capsys):
    monkeypatch.setattr(railmatch, "ENABLED", False)
    code, saved = graded()
    assert (code, saved["ok"]) == (0, True)
    assert rail_check(saved)["ok"] is False
    assert saved["rail_misfits"] == [{"line": "801", "misfits": 2, "runs": 4}]
    out = capsys.readouterr().out
    assert "advisory while the rail matcher is off" in out
    assert any(
        line.lstrip().startswith("CHECK") and "fit another trip" in line
        for line in out.splitlines()
    )


def test_a_failing_rail_check_fails_the_day_once_the_matcher_is_on(graded, monkeypatch):
    monkeypatch.setattr(railmatch, "ENABLED", True)
    monkeypatch.setattr(report, "rail_misfits", lambda con: [("801", 4, 2)])
    code, saved = graded()
    assert (code, saved["ok"], rail_check(saved)["ok"]) == (2, False, False)


def test_a_day_that_fails_another_check_still_fails_with_the_matcher_off(graded, monkeypatch):
    monkeypatch.setattr(railmatch, "ENABLED", False)
    code, saved = graded(other_check_fails=True)
    assert (code, saved["ok"], rail_check(saved)["ok"]) == (2, False, False)
