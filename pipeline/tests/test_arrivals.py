"""The rules arrivals.py follows, checked on a day small enough to work by hand.

Every expected value below comes from the table in fixture_day.py, not from
running the code. If one of these fails, either the code changed what it
measures or the fixture is wrong, and both are worth knowing before a backfill.
"""

from datetime import datetime

import pytest
from fixture_day import LA, SERVICE_DATE, build_raw, build_timetable, local

from howlate_pipeline import arrivals


@pytest.fixture(scope="module")
def result(tmp_path_factory):
    """Run the real pipeline steps on the fixture day, once for every test."""
    root = tmp_path_factory.mktemp("day")
    raw = build_raw(root / "raw")
    timetable = build_timetable(root / "gtfs_bus")

    con = arrivals.connect()
    files = arrivals.local_files(raw, SERVICE_DATE)
    arrivals.load_observations(con, files, SERVICE_DATE)
    arrivals.load_schedule(con, {"LACMTA": timetable}, SERVICE_DATE)
    arrivals.match(con, SERVICE_DATE)

    result = con.sql("""
        SELECT trip_id, stop_sequence, source, delay_seconds,
               epoch(scheduled_time) AS scheduled, epoch(actual_time) AS actual,
               is_origin, is_terminus
        FROM arrivals
    """).fetchall()
    return result


@pytest.fixture(scope="module")
def rows(result):
    """The same rows keyed by trip and stop. Duplicates collapse here, which is
    why the row count is checked on `result` instead."""
    keys = ["source", "delay", "scheduled", "actual", "is_origin", "is_terminus"]
    return {(trip, seq): dict(zip(keys, rest, strict=True)) for trip, seq, *rest in result}


def at(moment: datetime) -> int:
    return int(moment.timestamp())


def test_every_scheduled_stop_has_exactly_one_row(result, rows):
    assert len(result) == 6
    assert sorted(rows) == [
        ("T1", 1), ("T1", 2), ("T1", 3), ("T1", 4), ("T2", 1), ("T2", 2),
    ]  # fmt: skip


def test_first_stop_is_the_last_stopped_at_and_a_departure(rows):
    # Arrived to wait at 07:50, left at 08:01:30. Scheduled to arrive at 07:58
    # and leave at 08:00; the delay is measured from the departure.
    stop = rows[("T1", 1)]
    assert stop["source"] == "origin_departure"
    assert stop["actual"] == at(local(18, 8, 1, 30))
    assert stop["delay"] == 90


def test_mid_route_arrival_is_the_first_stopped_at(rows):
    # The 08:11 approach and the 08:12:30 dwell are both ignored, and the delay
    # is measured from the 08:10 arrival, not the 08:11 departure.
    stop = rows[("T1", 2)]
    assert stop["source"] == "stopped_at"
    assert stop["actual"] == at(local(18, 8, 12))
    assert stop["delay"] == 120


def test_only_approaches_uses_the_last_one(rows):
    stop = rows[("T1", 3)]
    assert stop["source"] == "approach"
    assert stop["actual"] == at(local(18, 8, 21))
    assert stop["delay"] == 120  # from the 08:19 arrival, not the 08:20 departure


def test_a_stop_nobody_saw_still_has_a_row(rows):
    stop = rows[("T1", 4)]
    assert stop["source"] == "none"
    assert stop["delay"] is None
    assert stop["actual"] is None
    assert stop["is_terminus"]


def test_a_time_past_24_00_lands_on_the_next_calendar_day(rows):
    # "25:30:00" on the 18th is 01:30 on the 19th, not 01:30 on the 18th.
    stop = rows[("T2", 2)]
    assert stop["scheduled"] == at(local(19, 1, 30))
    assert stop["delay"] == 180


def test_a_trip_crossing_midnight_is_read_from_the_next_partition(rows):
    # Both T2 reports are after 00:00 UTC on the 19th, so they live only in
    # dt=2026-08-19. Reading the service date's own partition alone would
    # leave T2 unobserved.
    assert rows[("T2", 1)]["delay"] == 60
    assert rows[("T2", 2)]["source"] == "stopped_at"


def test_reports_from_the_previous_service_day_are_ignored(rows):
    # The 17th's T1 reported stop 2 at 00:05 on the 18th, before this day's T1
    # reached it. Counting it would make the arrival eight hours early.
    assert rows[("T1", 2)]["actual"] == at(local(18, 8, 12))


def test_reports_from_the_next_service_day_are_ignored(rows):
    # The 19th's T1 stopped at D, which this day's T1 never reported. Counting
    # it would turn an unobserved stop into one a day late.
    assert rows[("T1", 4)]["source"] == "none"


def test_partitions_cover_the_day_either_side():
    assert arrivals.partitions(SERVICE_DATE) == ["2026-08-17", "2026-08-18", "2026-08-19"]


def test_local_files_reads_only_those_partitions(tmp_path):
    raw = build_raw(tmp_path)
    stray = tmp_path / "vehicle_positions" / "dt=2026-08-25" / "hh=00" / "x.jsonl.gz"
    stray.parent.mkdir(parents=True)
    stray.write_bytes(b"")
    found = arrivals.local_files(raw, SERVICE_DATE)
    assert found
    assert not any("dt=2026-08-25" in path for path in found)


def test_fixture_moments_are_in_daylight_time():
    # Guards the fixture itself: every expected value above assumes UTC-7.
    assert local(18, 8, 0).utcoffset().total_seconds() == -7 * 3600
    assert local(18, 8, 0).tzinfo is LA
