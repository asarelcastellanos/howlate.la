"""The report runs on the fixture day and adds up to the fixture's own numbers.

Mostly a guard on the library: report.py is where the pipeline pulls single
rows out of DuckDB, which is the first thing a DuckDB upgrade broke.
"""

import ast
import json
from pathlib import Path

import duckdb
import pytest
from fixture_day import SERVICE_DATE, local, run_day

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


def test_the_saved_report_holds_every_check_and_the_overall_result(con):
    saved = report.document(con, SERVICE_DATE)
    assert saved["service_date"] == "2026-08-18"
    assert saved["stats"]["scheduled_stops"] == 8
    names = [check["name"] for check in saved["checks"]]
    assert names == [
        *report.EXPECTED,
        "terminus_stopped",
        "ambiguous",
        "feeds",
        "silent_lines",
        "explained_lines",
    ]
    # The fixture has only the bus feed, so the feeds check fails, and with it
    # the day.
    feeds = next(check for check in saved["checks"] if check["name"] == "feeds")
    assert (feeds["value"], feeds["ok"]) == (1, False)
    assert saved["ok"] is False


def test_the_printed_and_saved_reports_agree(con, capsys):
    printed_ok = report.show(con, SERVICE_DATE)
    lines = [
        line.lstrip()
        for line in capsys.readouterr().out.splitlines()
        if line.lstrip().startswith(("ok ", "CHECK"))
    ]
    saved = report.document(con, SERVICE_DATE)
    assert printed_ok == saved["ok"]
    assert len(lines) == len(saved["checks"])
    for line, check in zip(lines, saved["checks"], strict=True):
        assert line.lstrip().startswith("ok" if check["ok"] else "CHECK"), check["name"]


def test_saving_the_same_day_twice_writes_the_same_bytes(con, tmp_path):
    first = report.save(report.document(con, SERVICE_DATE), tmp_path / "a.json").read_bytes()
    second = report.save(report.document(con, SERVICE_DATE), tmp_path / "b.json").read_bytes()
    assert first == second
    assert json.loads(first)["service_date"] == "2026-08-18"


def test_silent_lines_come_out_in_the_same_order_every_time():
    con = duckdb.connect()
    con.execute(
        "CREATE TABLE arrivals AS SELECT * FROM (VALUES "
        "('LACMTA', '33', 'none'), ('LACMTA', '4', 'none'), ('LACMTA_Rail', '801', 'none'), "
        "('LACMTA', '2', 'none'), ('LACMTA', '2', 'none')) t(agency, line, source)"
    )
    # Line 2 has the most scheduled stops; the three ties follow by name.
    assert report.silent_lines(con) == [
        ("LACMTA", "2", 2), ("LACMTA", "33", 1), ("LACMTA", "4", 1), ("LACMTA_Rail", "801", 1),
    ]  # fmt: skip


def arrivals_of(*rows: tuple[str, str]):
    """A bare arrivals table holding only what the silent-line checks read.

    The two empty tables are there because checks() reads them for explained_lines.
    """
    con = duckdb.connect()
    con.execute("CREATE TABLE observed (agency VARCHAR, trip_id VARCHAR)")
    con.execute(
        "CREATE TABLE listed_trips (agency VARCHAR, trip_id VARCHAR, route_id VARCHAR, "
        "service_active BOOLEAN, service_later BOOLEAN)"
    )
    values = ", ".join(f"('LACMTA', '{line}', '{source}')" for line, source in rows)
    con.execute(f"CREATE TABLE arrivals AS SELECT * FROM (VALUES {values}) t(agency, line, source)")
    return con


def silent_check(con, stats):
    return next(c for c in report.checks(con, stats) if c["name"] == "silent_lines")


@pytest.mark.parametrize("line", ["9", "22"])
def test_a_silent_event_only_line_passes_the_check_and_is_listed_apart(con, line):
    shuttles = arrivals_of((line, "none"), (line, "none"), ("720", "stopped_at"))
    check = silent_check(shuttles, report.summarise(con))
    assert (check["value"], check["ok"]) == (0, True)
    assert report.silent_lines(shuttles) == []
    assert report.silent_event_lines(shuttles) == [("LACMTA", line, 2)]


def test_a_silent_line_that_is_not_event_only_still_fails_the_check(con):
    # Line 9 beside it stays out of the count, so the failure is line 33's alone.
    mixed = arrivals_of(("9", "none"), ("33", "none"), ("720", "stopped_at"))
    check = silent_check(mixed, report.summarise(con))
    assert (check["value"], check["ok"]) == (1, False)
    assert report.silent_lines(mixed) == [("LACMTA", "33", 1)]
    assert report.silent_event_lines(mixed) == [("LACMTA", "9", 1)]


def test_a_scheduled_line_697_that_nothing_was_seen_on_fails_the_check(con):
    # Line 697 reported on all 6 days it was scheduled, so silence there is an
    # outage. It is a stadium shuttle but is not exempt.
    outage = arrivals_of(("697", "none"), ("697", "none"), ("720", "stopped_at"))
    check = silent_check(outage, report.summarise(con))
    assert (check["value"], check["ok"]) == (1, False)
    assert report.silent_lines(outage) == [("LACMTA", "697", 2)]
    assert report.silent_event_lines(outage) == []


@pytest.mark.parametrize("line", ["9", "22"])
def test_an_event_only_line_that_was_seen_is_not_listed_as_silent(line):
    seen = arrivals_of((line, "approach"), (line, "none"), ("720", "stopped_at"))
    assert report.silent_lines(seen) == []
    assert report.silent_event_lines(seen) == []


def test_the_saved_report_lists_silent_event_lines_apart_from_silent_lines(tmp_path):
    # The fixture's one line, renamed to a shuttle and never seen.
    con = run_day(tmp_path)
    con.execute(
        "UPDATE arrivals SET line = '9', source = 'none', actual_time = NULL, delay_seconds = NULL"
    )
    saved = report.document(con, SERVICE_DATE)
    assert saved["silent_event_lines"] == [{"agency": "LACMTA", "line": "9", "scheduled_stops": 8}]
    assert saved["silent_lines"] == []
    silent = next(check for check in saved["checks"] if check["name"] == "silent_lines")
    assert silent["ok"] is True


def test_the_printed_report_labels_silent_event_lines_as_informational(tmp_path, capsys):
    con = run_day(tmp_path)
    con.execute(
        "UPDATE arrivals SET line = '9', source = 'none', actual_time = NULL, delay_seconds = NULL"
    )
    report.show(con, SERVICE_DATE)
    out = capsys.readouterr().out
    assert "info LACMTA 9: event-only line, 8 scheduled stops, nothing observed, not checked" in out


def test_the_exempt_lines_are_event_only_lines_in_the_collector():
    # The packages install separately and neither may import the other, so the
    # collector's file is parsed as text rather than imported.
    here = Path(__file__).resolve()
    root = here.parents[2] if len(here.parents) > 2 else None
    if root is None or not (root / "collector").is_dir():
        # The container job mounts only pipeline/tests, at /tests. The checkout
        # job has the whole repo and runs this.
        pytest.skip("collector source is not beside the tests, as in the container job")
    # No exists() guard: if routes.py moves, this raises and fails the test.
    routes = root / "collector/src/howlate_collector/routes.py"
    assigned = [
        node.value
        for node in ast.parse(routes.read_text()).body
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "EVENT_ONLY" for t in node.targets)
    ]
    assert len(assigned) == 1, "EVENT_ONLY is no longer one top-level assignment in routes.py"
    assert report.EVENT_ONLY <= frozenset(ast.literal_eval(assigned[0]))


def test_a_save_killed_mid_write_leaves_no_report(tmp_path, monkeypatch):
    # The write dies halfway, as a killed process would. Whatever is on disk
    # must not be the report itself, or the day would count as done.
    real_write = Path.write_text

    def dies_halfway(self, data, *args, **kwargs):
        real_write(self, data[: len(data) // 2])
        raise OSError("killed while writing")

    monkeypatch.setattr(Path, "write_text", dies_halfway)
    path = tmp_path / "report.json"
    with pytest.raises(OSError):
        report.save({"service_date": "2026-08-18", "ok": True}, path)
    assert not path.exists()


def test_the_printed_report_survives_a_day_with_nothing_timed(tmp_path, capsys):
    # A fresh day, emptied, so the shared fixture is left alone.
    con = run_day(tmp_path)
    con.execute("CREATE OR REPLACE TABLE arrivals AS SELECT * FROM arrivals WHERE false")
    report.show(con, SERVICE_DATE)
    assert "median n/a" in capsys.readouterr().out


def stopped(trip, seq, stop):
    """One more STOPPED_AT report on the fixture day, in the shape REPORTS uses."""
    return (trip, SERVICE_DATE, seq, stop, "STOPPED_AT", local(18, 9, 0), "5816")


def check_named(con, name):
    return next(c for c in report.checks(con, report.summarise(con)) if c["name"] == name)


def matched_check(con):
    return check_named(con, "matched_rate")


def with_joined_filler(con, count):
    """Add `count` observations that join, so the explained share of the day is small.

    The fixture day has only 5 observations, so one explained trip is 17% of it.
    """
    con.execute(
        "INSERT INTO scheduled BY NAME SELECT 'LACMTA' AS agency, 'F' AS trip_id, "
        "range AS stop_sequence FROM range(1, ?)",
        [count + 1],
    )
    con.execute(
        "INSERT INTO observed BY NAME SELECT 'LACMTA' AS agency, 'F' AS trip_id, "
        "range AS stop_sequence, 1 AS distinct_stop_ids FROM range(1, ?)",
        [count + 1],
    )


def test_a_trip_listed_under_a_later_service_is_explained_not_failed(tmp_path):
    # T9 is in trips.txt under a service that starts on 1 September, so it has
    # no scheduled stops on the 18th. Five observations join and this one cannot.
    con = run_day(tmp_path, extra_reports=[stopped("T9", 1, "A")], later_service=True)
    stats = report.summarise(con)
    assert stats["observations"] == 6
    assert stats["join_rate"] == pytest.approx(100 * 5 / 6)
    assert (stats["explained"], stats["explained_trips"]) == (1, 1)
    check = matched_check(con)
    assert (check["value"], check["ok"]) == (100, True)


@pytest.mark.parametrize("cause", ["expired", "removed", "no_row"])
def test_a_trip_under_a_service_that_is_not_later_starting_stays_unexplained(tmp_path, cause):
    # T9's service is not running on the 18th, but only a later start date was
    # ever measured as a cause. An expired service, one a calendar_dates row
    # removed for the day, and one with no calendar.txt row are not explained.
    con = run_day(tmp_path, extra_reports=[stopped("T9", 1, "A")], t9_service=cause)
    stats = report.summarise(con)
    assert (stats["explained"], stats["explained_trips"]) == (0, 0)
    check = matched_check(con)
    assert check["value"] == pytest.approx(100 * 5 / 6)
    assert check["ok"] is False


def test_a_trip_one_copy_lists_later_and_another_lists_expired_is_not_explained(tmp_path):
    # Every listing has to be later-start. One copy saying "starts later" does
    # not outweigh another saying the service already ended.
    con = run_day(
        tmp_path,
        extra_reports=[stopped("T9", 1, "A")],
        later_service=True,
        other_copy_lists_t9="expired",
    )
    assert (report.summarise(con)["explained"], matched_check(con)["ok"]) == (0, False)


def test_a_trip_in_no_timetable_still_fails_the_check(tmp_path):
    con = run_day(tmp_path, extra_reports=[stopped("T8", 1, "A")], later_service=True)
    stats = report.summarise(con)
    assert (stats["explained"], stats["explained_trips"]) == (0, 0)
    check = matched_check(con)
    assert check["value"] == pytest.approx(100 * 5 / 6)
    assert check["ok"] is False


def test_a_trip_only_another_copy_lists_under_a_later_service_is_explained(tmp_path):
    # The copy graded against lacks T9, as the 2026-11-14 rail copy in force
    # lacked 142 trips that the copy fetched that day lists under later services.
    reports = [stopped("T9", 1, "A")]
    con = run_day(tmp_path / "a", extra_reports=reports, other_copy_lists_later=True)
    assert (report.summarise(con)["explained"], matched_check(con)["ok"]) == (1, True)
    # Without the other copy read, nothing lists T9 and it fails as before.
    con = run_day(tmp_path / "b", extra_reports=reports)
    assert (report.summarise(con)["explained"], matched_check(con)["ok"]) == (0, False)


def test_an_unlisted_stop_on_a_running_trip_is_not_explained(tmp_path):
    # T1 runs today, so a stop_sequence its timetable lacks is a real join
    # failure, whatever trips.txt says about T1.
    con = run_day(tmp_path, extra_reports=[stopped("T1", 9, "Z")], later_service=True)
    assert report.summarise(con)["explained"] == 0
    assert matched_check(con)["ok"] is False


def test_a_trip_any_copy_lists_under_a_running_service_is_not_explained(tmp_path):
    # The chosen copy runs T1 today but has no stop 9, so this observation has
    # no scheduled stop. A second copy, whose calendar runs nothing on the 18th,
    # lists T1 under a service that is not running. One copy listing T1 as
    # running is enough to call it a real join failure, so it must not be
    # explained. Taking the second copy's word for it would hide the failure.
    con = run_day(tmp_path, extra_reports=[stopped("T1", 9, "Z")], other_copy_expired=True)
    assert (report.summarise(con)["explained"], matched_check(con)["ok"]) == (0, False)


def test_the_explained_counts_are_printed_and_saved(tmp_path, capsys):
    con = run_day(tmp_path, extra_reports=[stopped("T9", 1, "A")], later_service=True)
    report.show(con, SERVICE_DATE)
    out = capsys.readouterr().out
    assert "1 observations on 1 trips" in out
    saved = report.document(con, SERVICE_DATE)
    assert saved["stats"]["explained"] == 1
    assert saved["explained_unmatched"] == [{"agency": "LACMTA", "observations": 1, "trips": 1}]
    assert len(saved["notes"]) == 1
    cap = next(check for check in saved["checks"] if check["name"] == "explained_pct")
    assert (cap["value"], cap["ok"]) == (saved["stats"]["explained_pct"], False)
    assert "start date is after" in saved["notes"][0]


def test_a_day_with_nothing_explained_prints_and_saves_no_note(con, capsys):
    report.show(con, SERVICE_DATE)
    assert "explained:" not in capsys.readouterr().out
    saved = report.document(con, SERVICE_DATE)
    assert saved["stats"]["explained"] == 0
    assert (saved["explained_unmatched"], saved["notes"]) == ([], [])
    assert matched_check(con)["value"] == saved["stats"]["join_rate"] == 100


def test_a_small_explained_share_passes_the_cap(tmp_path):
    con = run_day(tmp_path, extra_reports=[stopped("T9", 1, "A")], later_service=True)
    with_joined_filler(con, 200)
    stats = report.summarise(con)
    assert (stats["explained"], stats["observations"]) == (1, 206)
    cap = check_named(con, "explained_pct")
    assert cap["value"] == pytest.approx(100 / 206)
    assert cap["ok"] is True


def test_a_day_where_most_trips_are_explained_fails_the_cap_but_not_matched_rate(tmp_path):
    # One explained observation in six is 16.7%. A service-selection bug that
    # hid most of a day would look like this, and matched_rate alone cannot tell.
    con = run_day(tmp_path, extra_reports=[stopped("T9", 1, "A")], later_service=True)
    cap = check_named(con, "explained_pct")
    assert cap["value"] == pytest.approx(100 / 6)
    assert (cap["ok"], matched_check(con)["ok"]) == (False, True)


@pytest.mark.parametrize(
    ("percent", "passes"),
    [(4.9, True), (5.0, True), (5.005, False), (5.1, False)],
)
def test_the_explained_cap_is_five_percent_and_includes_five(con, percent, passes):
    # The range check is low <= value <= high, so exactly 5.0 passes.
    stats = report.summarise(con) | {"explained_pct": percent}
    cap = next(c for c in report.checks(con, stats) if c["name"] == "explained_pct")
    assert cap["ok"] is passes


def test_one_explained_observation_in_twenty_is_exactly_the_cap_and_passes(tmp_path):
    con = run_day(tmp_path, extra_reports=[stopped("T9", 1, "A")], later_service=True)
    with_joined_filler(con, 14)
    stats = report.summarise(con)
    assert (stats["explained"], stats["observations"]) == (1, 20)
    cap = check_named(con, "explained_pct")
    assert (cap["value"], cap["ok"]) == (5.0, True)


def test_a_day_with_nothing_explained_passes_the_cap(con):
    cap = check_named(con, "explained_pct")
    assert (cap["value"], cap["ok"]) == (0, True)


def add_trips(con, route_id, *, explained=0, matched=0, agency="LACMTA"):
    """Observed trips on one route, one observation each.

    `explained` trips are listed only under a later-start service. `matched`
    trips are listed under a running one and have a scheduled stop to join.
    """
    for kind, count, running in (("E", explained, False), ("M", matched, True)):
        for i in range(count):
            trip_id = f"{kind}-{agency}-{route_id}-{i}"
            con.execute(
                "INSERT INTO listed_trips VALUES (?, ?, ?, ?, ?)",
                [agency, trip_id, route_id, running, not running],
            )
            con.execute(
                "INSERT INTO observed BY NAME SELECT ? AS agency, ? AS trip_id, "
                "1 AS stop_sequence, 1 AS distinct_stop_ids",
                [agency, trip_id],
            )
            if running:
                con.execute(
                    "INSERT INTO scheduled BY NAME SELECT ? AS agency, ? AS trip_id, "
                    "1 AS stop_sequence",
                    [agency, trip_id],
                )


def test_one_line_whose_observed_trips_are_all_explained_fails_its_own_check(tmp_path):
    # Rail is about 4% of observations, so six explained trips on one line are
    # far under the network cap and matched_rate counts them as matched. Only
    # the per-line check can see that the whole line was hidden.
    con = run_day(tmp_path)
    with_joined_filler(con, 2000)
    add_trips(con, "801", explained=6)
    assert check_named(con, "matched_rate")["ok"] is True
    assert check_named(con, "explained_pct")["ok"] is True
    lines = check_named(con, "explained_lines")
    assert (lines["value"], lines["ok"]) == (1, False)
    assert report.fully_explained_lines(con) == [("LACMTA", "801", 6)]


def test_a_line_with_some_explained_trips_and_some_matched_passes(tmp_path):
    # The real 2026-11-14 shape: route 801 had 338 explained trips and 233 that
    # matched, so the line was only partly hidden and nothing is wrong with it.
    con = run_day(tmp_path)
    with_joined_filler(con, 2000)
    add_trips(con, "801", explained=6, matched=3)
    lines = check_named(con, "explained_lines")
    assert (lines["value"], lines["ok"]) == (0, True)


@pytest.mark.parametrize(("trips", "failed"), [(4, 0), (5, 1)])
def test_a_line_needs_five_observed_trips_to_trip_the_check(tmp_path, trips, failed):
    con = run_day(tmp_path)
    with_joined_filler(con, 2000)
    add_trips(con, "801", explained=trips)
    assert check_named(con, "explained_lines")["value"] == failed


def test_the_line_is_the_route_id_without_its_version_suffix(tmp_path):
    # "720-13201" is line 720. Trips on two route ids of one line add up.
    con = run_day(tmp_path)
    with_joined_filler(con, 2000)
    add_trips(con, "801-1", explained=3)
    add_trips(con, "801-2", explained=3)
    assert report.fully_explained_lines(con) == [("LACMTA", "801", 6)]


def test_the_same_line_code_in_two_feeds_is_counted_apart(tmp_path):
    con = run_day(tmp_path)
    with_joined_filler(con, 2000)
    add_trips(con, "801", explained=3)
    add_trips(con, "801", explained=3, agency="LACMTA_Rail")
    assert check_named(con, "explained_lines")["value"] == 0


def test_a_day_with_nothing_explained_passes_the_line_check(con):
    lines = check_named(con, "explained_lines")
    assert (lines["value"], lines["ok"]) == (0, True)
