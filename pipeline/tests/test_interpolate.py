"""Bus stops the feed skipped get a time from the reports either side of them.

Every expected value comes from the table below, worked by hand, not from
running the code. Service day 2026-08-18, so GTFS times count from 07:00 UTC.

Six bus stops, S1 to S6, on one meridian at latitude 34.000, 34.001, ... 34.005.
A thousandth of a degree is 110.574 m, so the stops are equally spaced and a
report halfway between two stops sits 0.5 of a step from each. The timetable
runs a stop every 2 minutes from 08:00 (S1) to 08:10 (S6), on all trips.

    T1  V1 STOPPED_AT stop 1 at 08:00:00, lat 34.000   origin
        V1 STOPPED_AT stop 2 at 08:01:00, lat 34.001
        V1 IN_TRANSIT_TO stop 4 at 08:04:00, lat 34.0025, halfway from S3 to S4
        V1 STOPPED_AT stop 5 at 08:05:30, lat 34.004
        Stop 3 has no report. S2 is step 1 of the route, the report before; the
        08:04 report is step 2.5. S3 is step 2, so it is (2-1) / (2.5-1) = 2/3 of
        the way from 08:01:00 to 08:04:00, which is 08:03:00. Scheduled 08:04, so
        it is 60 s early.
        Stop 6 has nothing after it, so there is no report after it.

    T2  V1 STOPPED_AT stop 2 at 09:00:00, lat 34.001
        V1 IN_TRANSIT_TO stop 4 at 09:10:00, lat 34.0025
        Stop 3 is 2/3 of the way, but the two reports are 600 s apart, over the
        300 s limit, so it stays none.

    T3  V1 reports only stop 4 and stop 5, at 10:06:00 and 10:08:00. Stops 2 and
        3 have no report before them, so they stay none. Stop 1 is the origin.

    T4  V1 STOPPED_AT stop 2 at 11:01:00, V2 IN_TRANSIT_TO stop 4 at 11:04:00.
        Two buses, so neither pairs with the other and stop 3 stays none.

    T5  V1 STOPPED_AT stop 2 at 12:01:00, lat 34.001
        V1 IN_TRANSIT_TO stop 4 at 12:03:00, lat 34.0015, which is before S3 on
        the route. The bus had not reached S3 when the later report was sent, so
        S3 does not lie between the two and it stays none.

    T6  V1 STOPPED_AT stop 2 at 13:01:00 and IN_TRANSIT_TO stop 4 at 13:04:00,
        as T1, but both reports have no position. Stop 3 stays none.

    R1  A rail trip with the same shape as T1: reports at stops 2 and 4 either
        side of stop 3. Rail is left alone, so stop 3 stays none.
"""

import gzip
import json
from datetime import datetime
from pathlib import Path

import pytest
from fixture_day import _DOW, SERVICE_DATE, UTC, local, write_csv

from howlate_pipeline import arrivals

LON = -118.0


def clock(stop: int) -> str:
    """Scheduled time of a stop: 08:00 for S1 and two more minutes for each."""
    return f"08:{(stop - 1) * 2:02d}:00"


def lat(step: float) -> float:
    """Latitude `step` stops from S1, with S1 at 34.000."""
    return round(34.0 + step * 0.001, 6)


# trip, stop_sequence, status, moment, vehicle, latitude (None for no position)
REPORTS = [
    ("T1", 1, "STOPPED_AT", local(18, 8, 0, 0), "V1", lat(0)),
    ("T1", 2, "STOPPED_AT", local(18, 8, 1, 0), "V1", lat(1)),
    ("T1", 4, "IN_TRANSIT_TO", local(18, 8, 4, 0), "V1", lat(2.5)),
    ("T1", 5, "STOPPED_AT", local(18, 8, 5, 30), "V1", lat(4)),
    ("T2", 2, "STOPPED_AT", local(18, 9, 0, 0), "V1", lat(1)),
    ("T2", 4, "IN_TRANSIT_TO", local(18, 9, 10, 0), "V1", lat(2.5)),
    ("T3", 4, "IN_TRANSIT_TO", local(18, 10, 6, 0), "V1", lat(2.5)),
    ("T3", 5, "STOPPED_AT", local(18, 10, 8, 0), "V1", lat(4)),
    ("T4", 2, "STOPPED_AT", local(18, 11, 1, 0), "V1", lat(1)),
    ("T4", 4, "IN_TRANSIT_TO", local(18, 11, 4, 0), "V2", lat(2.5)),
    ("T5", 2, "STOPPED_AT", local(18, 12, 1, 0), "V1", lat(1)),
    ("T5", 4, "IN_TRANSIT_TO", local(18, 12, 3, 0), "V1", lat(1.5)),
    ("T6", 2, "STOPPED_AT", local(18, 13, 1, 0), "V1", None),
    ("T6", 4, "IN_TRANSIT_TO", local(18, 13, 4, 0), "V1", None),
]
RAIL_REPORTS = [
    ("R1", 2, "STOPPED_AT", local(18, 14, 1, 0), "RV1", lat(1)),
    ("R1", 4, "IN_TRANSIT_TO", local(18, 14, 4, 0), "RV1", lat(2.5)),
]


def build_timetable(directory: Path, trips: list[str], route: str) -> Path:
    """A timetable of these trips, each with the six stops and clock() times."""
    directory.mkdir(parents=True, exist_ok=True)
    write_csv(
        directory / "calendar.txt",
        ["service_id", *_DOW, "start_date", "end_date"],
        [["WK", *["1"] * 7, "20260101", "20261231"]],
    )
    write_csv(directory / "calendar_dates.txt", ["service_id", "date", "exception_type"], [])
    write_csv(
        directory / "trips.txt",
        ["route_id", "service_id", "trip_id", "direction_id"],
        [[route, "WK", trip, "0"] for trip in trips],
    )
    write_csv(
        directory / "stop_times.txt",
        ["trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence"],
        [[trip, clock(seq), clock(seq), f"S{seq}", seq] for trip in trips for seq in range(1, 7)],
    )
    write_csv(
        directory / "stops.txt",
        ["stop_id", "stop_name", "stop_lat", "stop_lon"],
        [[f"S{seq}", f"Stop {seq}", lat(seq - 1), LON] for seq in range(1, 7)],
    )
    return directory


def build_raw(directory: Path, agency: str, reports: list[tuple]) -> None:
    """One archive file per UTC hour, as the collector writes them."""
    by_file: dict[Path, list[dict]] = {}
    for trip, seq, status, moment, vehicle, latitude in reports:
        stamp = moment.astimezone(UTC)
        folder = directory / "vehicle_positions" / f"dt={stamp:%Y-%m-%d}" / f"hh={stamp:%H}"
        path = folder / f"vehicle_positions-{stamp:%Y%m%dT%H}0000Z-{agency}.jsonl.gz"
        position = (
            {} if latitude is None else {"position": {"latitude": latitude, "longitude": LON}}
        )
        by_file.setdefault(path, []).append(
            {
                "received_at": stamp.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                "agency": agency,
                "payload": {
                    "vehicle": {
                        "trip": {"tripId": trip, "startDate": SERVICE_DATE},
                        "currentStopSequence": seq,
                        "currentStatus": status,
                        "timestamp": str(int(moment.timestamp())),
                        "stopId": f"S{seq}",
                        "vehicle": {"id": vehicle},
                        **position,
                    }
                },
            }
        )
    for path, rows in by_file.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(path, "wt") as handle:
            handle.writelines(json.dumps(row) + "\n" for row in rows)


def graded(root: Path, reports=REPORTS, rail_reports=RAIL_REPORTS, max_gap=None):
    """The fixture day through load, match and interpolate."""
    build_raw(root / "raw", "LACMTA", reports)
    build_raw(root / "raw", "LACMTA_Rail", rail_reports)
    bus = build_timetable(root / "gtfs_bus", sorted({r[0] for r in reports}), "720-1")
    rail = build_timetable(root / "gtfs_rail", sorted({r[0] for r in rail_reports}), "801-1")
    con = arrivals.connect()
    arrivals.load_observations(con, arrivals.local_files(root / "raw", SERVICE_DATE), SERVICE_DATE)
    arrivals.load_schedule(con, {"LACMTA": bus, "LACMTA_Rail": rail}, SERVICE_DATE)
    arrivals.match(con, SERVICE_DATE)
    if max_gap is None:
        arrivals.interpolate(con)
    else:
        arrivals.interpolate(con, max_gap)
    return con


def stop(con, trip: str, seq: int) -> dict:
    keys = ["source", "delay", "actual", "vehicle", "departure", "in_transit_seen"]
    row = con.sql(
        "SELECT source, delay_seconds, epoch(actual_time), vehicle_id, epoch(departure_time), "
        f"in_transit_seen FROM arrivals WHERE trip_id = '{trip}' AND stop_sequence = {seq}"
    ).fetchone()
    return dict(zip(keys, row, strict=True))


def at(moment: datetime) -> int:
    return int(moment.timestamp())


@pytest.fixture(scope="module")
def con(tmp_path_factory):
    return graded(tmp_path_factory.mktemp("interpolate"))


def test_a_skipped_stop_is_placed_by_how_far_along_it_sits(con):
    # 2/3 of the way from 08:01:00 to 08:04:00 is 08:03:00, scheduled 08:04:00.
    skipped = stop(con, "T1", 3)
    assert skipped["source"] == "interpolated"
    assert skipped["actual"] == at(local(18, 8, 3, 0))
    assert skipped["delay"] == -60


def test_an_interpolated_stop_names_the_vehicle_and_has_no_departure(con):
    skipped = stop(con, "T1", 3)
    assert skipped["vehicle"] == "V1"
    # It never reported stopping there, so there is no departure to give.
    assert skipped["departure"] is None
    assert skipped["in_transit_seen"] is False


def test_stops_that_were_seen_keep_their_source_and_time(con):
    assert stop(con, "T1", 1)["source"] == "origin_departure"
    assert stop(con, "T1", 2)["source"] == "stopped_at"
    assert stop(con, "T1", 2)["actual"] == at(local(18, 8, 1, 0))
    approach = stop(con, "T1", 4)
    assert approach["source"] == "approach"
    assert approach["actual"] == at(local(18, 8, 4, 0))


def test_the_last_stop_has_no_report_after_it_and_stays_none(con):
    last = stop(con, "T1", 6)
    assert last["source"] == "none"
    assert last["actual"] is None
    assert last["delay"] is None


def test_stops_before_a_vehicles_first_report_stay_none(con):
    for seq in (2, 3):
        assert stop(con, "T3", seq)["source"] == "none"
    # The same vehicle's later stops were seen, so the trip is not simply unseen.
    assert stop(con, "T3", 4)["source"] == "approach"


def test_two_reports_further_apart_than_the_limit_leave_the_stop_none(con):
    assert stop(con, "T2", 3)["source"] == "none"


def test_the_limit_is_inclusive(tmp_path):
    # T2's reports are exactly 600 s apart.
    at_limit = graded(tmp_path, max_gap=600)
    assert stop(at_limit, "T2", 3)["source"] == "interpolated"
    # 08:03:00 is 2/3 of the way from 08:01:00 to 08:04:00, so 09:06:40 is 2/3
    # of the way from 09:00:00 to 09:10:00.
    assert stop(at_limit, "T2", 3)["actual"] == at(local(18, 9, 6, 40))
    just_under = graded(tmp_path / "under", max_gap=599)
    assert stop(just_under, "T2", 3)["source"] == "none"


def test_reports_from_two_vehicles_are_not_paired(con):
    assert stop(con, "T4", 3)["source"] == "none"


def test_a_stop_the_bus_had_not_reached_by_the_next_report_stays_none(con):
    assert stop(con, "T5", 3)["source"] == "none"


def test_reports_without_a_position_are_not_used(con):
    assert stop(con, "T6", 3)["source"] == "none"


def test_rail_is_left_alone(con):
    assert stop(con, "R1", 3)["source"] == "none"


def test_a_rerun_gives_the_same_rows(tmp_path, con):
    again = graded(tmp_path)
    query = (
        "SELECT agency, trip_id, stop_sequence, source, delay_seconds, epoch(actual_time), "
        "vehicle_id FROM arrivals ORDER BY agency, trip_id, stop_sequence"
    )
    assert again.sql(query).fetchall() == con.sql(query).fetchall()


def test_the_trips_table_counts_only_stops_the_vehicle_reported(con):
    arrivals.trips(con)
    # T1 has reports at stops 1, 2, 4 and 5. Stop 3 was placed, not seen.
    observed = con.sql("SELECT stops_observed FROM trips WHERE trip_id = 'T1'").fetchone()[0]
    assert observed == 4
