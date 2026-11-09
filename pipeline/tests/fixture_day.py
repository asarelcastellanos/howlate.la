"""A hand-built service day, small enough to work out every answer by hand.

Service day 2026-08-18, a Tuesday. Los Angeles is on daylight time (UTC-7), so
GTFS times on this day count from 2026-08-18 07:00 UTC.

Two trips on line 720, both in the timetable and both with position reports:

    T1  stop 1 (A) 07:58, leaves 08:00   origin
        stop 2 (B) 08:10, leaves 08:11
        stop 3 (C) 08:19, leaves 08:20
        stop 4 (D) 08:30   terminus

    T2  stop 1 (E) 23:50   origin
        stop 2 (F) 25:30   terminus, which is 01:30 on 19 August

What the vehicles reported, and the answer each one should produce:

    T1 stop 1  STOPPED_AT 07:50, 07:58, 08:01:30
               the bus arrived to wait at 07:50 and left at 08:01:30, so this
               is a departure, 90 s late, labeled origin_departure
    T1 stop 2  IN_TRANSIT_TO 08:11, then STOPPED_AT 08:12:00 and 08:12:30
               the first STOPPED_AT is the arrival: 120 s late, stopped_at
    T1 stop 3  IN_TRANSIT_TO 08:19 and 08:21, never STOPPED_AT
               the last approach stands in: 120 s after the 08:19
               arrival, approach
    T1 stop 4  nothing
               a row with no delay, source none
    T2 stop 1  STOPPED_AT 23:51, 60 s after the scheduled departure
    T2 stop 2  STOPPED_AT 01:33 on 19 August, 180 s late

T3 is scheduled (12:00 and 12:15) and nothing ever reported it: a trip the
feed never saw.

Which vehicle, and when it left:

    T1 stops 1-2 are vehicle 5816; T1 switches to 5900 before stop 3
    departure_time is the last STOPPED_AT: 08:01:30 at stop 1, 08:12:30 at
    stop 2, and empty at stops 3 and 4, which never reported stopping
    T2 stop 2 has 6001 and 6002 in the same second; the lower id, 6001, wins

T2's reports are after midnight UTC, so they sit in the dt=2026-08-19
partition. Two reports belong to other service days and must be ignored: the
17th's T1 at stop 2, in the 2026-08-18 partition, and the 19th's T1 at stop 4,
in the 2026-08-19 partition.
"""

import csv
import gzip
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

SERVICE_DATE = "20260818"
LA = ZoneInfo("America/Los_Angeles")
UTC = ZoneInfo("UTC")


def local(day: int, hour: int, minute: int, second: int = 0) -> datetime:
    """A wall-clock moment in Los Angeles in August 2026."""
    return datetime(2026, 8, day, hour, minute, second, tzinfo=LA)


SCHEDULE = [
    # trip, stop_sequence, stop_id, arrival, departure
    # Arrival and departure differ at A, B and C, one stop per way of timing
    # an arrival, so a delay measured from the wrong one of the two fails.
    ("T1", 1, "A", "07:58:00", "08:00:00"),
    ("T1", 2, "B", "08:10:00", "08:11:00"),
    ("T1", 3, "C", "08:19:00", "08:20:00"),
    ("T1", 4, "D", "08:30:00", "08:30:00"),
    ("T2", 1, "E", "23:50:00", "23:50:00"),
    ("T2", 2, "F", "25:30:00", "25:30:00"),
    ("T3", 1, "G", "12:00:00", "12:00:00"),
    ("T3", 2, "H", "12:15:00", "12:15:00"),
]

REPORTS = [
    # trip, start date, stop_sequence, stop_id, status, moment, vehicle
    ("T1", SERVICE_DATE, 1, "A", "STOPPED_AT", local(18, 7, 50), "5816"),
    ("T1", SERVICE_DATE, 1, "A", "STOPPED_AT", local(18, 7, 58), "5816"),
    ("T1", SERVICE_DATE, 1, "A", "STOPPED_AT", local(18, 8, 1, 30), "5816"),
    ("T1", SERVICE_DATE, 2, "B", "IN_TRANSIT_TO", local(18, 8, 11), "5816"),
    ("T1", SERVICE_DATE, 2, "B", "STOPPED_AT", local(18, 8, 12), "5816"),
    ("T1", SERVICE_DATE, 2, "B", "STOPPED_AT", local(18, 8, 12, 30), "5816"),
    # T1 changes vehicles after stop 2: 5900 carries it on from here.
    ("T1", SERVICE_DATE, 3, "C", "IN_TRANSIT_TO", local(18, 8, 19), "5900"),
    ("T1", SERVICE_DATE, 3, "C", "IN_TRANSIT_TO", local(18, 8, 21), "5900"),
    ("T2", SERVICE_DATE, 1, "E", "STOPPED_AT", local(18, 23, 51), "6001"),
    # Two vehicles claim the same trip and stop in the same second. Rare, but
    # it must resolve the same way on every rerun: the lower id wins.
    ("T2", SERVICE_DATE, 2, "F", "STOPPED_AT", local(19, 1, 33), "6002"),
    ("T2", SERVICE_DATE, 2, "F", "STOPPED_AT", local(19, 1, 33), "6001"),
    # The previous service day's T1, still reporting. Same trip and stop, so
    # only the start date keeps it out of this day's answer.
    ("T1", "20260817", 2, "B", "STOPPED_AT", local(18, 0, 5), "4100"),
    # The next service day's T1, at the stop this day never saw. Only the
    # start date keeps it from turning stop 4 into an observed arrival.
    ("T1", "20260819", 4, "D", "STOPPED_AT", local(19, 8, 30), "4200"),
]


def write_csv(path: Path, header: list[str], rows: list[list]) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def build_timetable(directory: Path, *, services: bool = True) -> Path:
    """A bus timetable holding T1 and T2.

    With services=False the calendar lists nothing running on the service day,
    which is what a copy fetched the morning after looks like.
    """
    directory.mkdir(parents=True, exist_ok=True)
    days = ["1"] * 7 if services else ["0"] * 7
    write_csv(
        directory / "calendar.txt",
        ["service_id", *_DOW, "start_date", "end_date"],
        [["WK", *days, "20260101", "20261231"]],
    )
    write_csv(directory / "calendar_dates.txt", ["service_id", "date", "exception_type"], [])
    write_csv(
        directory / "trips.txt",
        ["route_id", "service_id", "trip_id", "direction_id"],
        [
            ["720-13201", "WK", "T1", "0"],
            ["720-13201", "WK", "T2", "0"],
            ["720-13201", "WK", "T3", "1"],
        ],
    )
    write_csv(
        directory / "stop_times.txt",
        ["trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence"],
        [[trip, arrive, depart, stop, seq] for trip, seq, stop, arrive, depart in SCHEDULE],
    )
    return directory


_DOW = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def record(
    trip: str, start: str, seq: int, stop: str, status: str, moment: datetime, vehicle: str
) -> dict:
    """One line of the raw archive, shaped as the collector writes it."""
    return {
        "received_at": moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "agency": "LACMTA",
        "payload": {
            "vehicle": {
                "trip": {"tripId": trip, "startDate": start, "routeId": "720-13201"},
                "currentStopSequence": seq,
                "currentStatus": status,
                "timestamp": str(int(moment.timestamp())),
                "stopId": stop,
                "vehicle": {"id": vehicle},
            }
        },
    }


def build_raw(directory: Path) -> Path:
    """The archive layout: one file per UTC hour, under dt= and hh= partitions."""
    by_file: dict[Path, list[dict]] = {}
    for trip, start, seq, stop, status, moment, vehicle in REPORTS:
        moment_utc = moment.astimezone(UTC)
        folder = (
            directory / "vehicle_positions" / f"dt={moment_utc:%Y-%m-%d}" / f"hh={moment_utc:%H}"
        )
        path = folder / f"vehicle_positions-{moment_utc:%Y%m%dT%H}0000Z.jsonl.gz"
        by_file.setdefault(path, []).append(record(trip, start, seq, stop, status, moment, vehicle))

    for path, rows in by_file.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(path, "wt") as handle:
            for row in rows:
                handle.write(json.dumps(row) + "\n")
    return directory
