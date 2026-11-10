"""The report runs on the fixture day and adds up to the fixture's own numbers.

Mostly a guard on the library: report.py is where the pipeline pulls single
rows out of DuckDB, which is the first thing a DuckDB upgrade broke.
"""

import json
from pathlib import Path

import duckdb
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


def test_the_saved_report_holds_every_check_and_the_overall_result(con):
    saved = report.document(con, SERVICE_DATE)
    assert saved["service_date"] == "2026-08-18"
    assert saved["stats"]["scheduled_stops"] == 8
    names = [check["name"] for check in saved["checks"]]
    assert names == [*report.EXPECTED, "terminus_stopped", "ambiguous", "feeds", "silent_lines"]
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
