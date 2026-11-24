"""A hand-built rail day beside the bus day of fixture_day.py, with every answer worked by hand.

Service day 2026-08-18. Route 801 runs one way, direction 0, over seven stations
S1 to S7, 0.02 degrees of latitude apart, which is 2.2 km and well past the 300 m
a position can be from a station. Every trip stops at S1 at its first time and
at each next station 5 minutes later, so S7 is 30 minutes after S1.

    R1  leaves S1 at 10:00   service WK, runs today
    R2  leaves S1 at 10:20   service WK
    R3  leaves S1 at 10:40   service WK
    L1  leaves S1 at 10:30   service LATER, starts 1 September, so it is listed
                             with stops and has no scheduled stops today

Four vehicles drive S1 to S6. A vehicle that is `d` seconds late reports
STOPPED_AT at S1 at its departure and at S2 to S6, an IN_TRANSIT_TO report at S7
one minute before it is due and another one minute after, and a STOPPED_AT at S1
five minutes before it leaves. Its S7 arrival is the last approach, so it is
`d + 60` seconds late there.

    V1  drives R1, 30 s late. Reports R1 and startTime 10:00:00.
        The id is a running trip and the startTime is R1's first departure, so
        the run is trusted. R1 delays 30, 30, 30, 30, 30, 30, 90.
    V2  drives R2, 60 s late. Reports R1, a stale id, and startTime 10:20:00.
        R1 is 20 minutes off the startTime, so the id fails. R2 fits to 60 s and
        the next trip, R3, to 1,140 s, so it is matched to R2.
        R2 delays 60, 60, 60, 60, 60, 60, 120.
    V3  drives R3, 90 s late. Reports L1 and startTime 10:30:00.
        L1 has no running service, so the id fails. R3 fits to 90 s and R2 to
        1,290 s, so it is matched to R3. R3 delays 90, 90, 90, 90, 90, 90, 150.
    V4  drives 600 s behind R1, which is 600 s ahead of R2. Reports R2 and
        startTime 10:05:00, 15 minutes off R2's first departure, so the id fails.
        R1 and R2 both fit to 600 s, which is not within 120 s, so it is left
        ungraded and adds no delay to any trip.

    V5  drives X1 of route 802, which runs exactly the times of R2, 30 s late.
        Reports L1, a later-start id, startTime 10:30:00 and routeId 802. R2
        and X1 explain its stations equally, so the reported route breaks the
        tie. It is matched to X1, and R2 keeps only V2's delays.
        X1 delays 30, 30, 30, 30, 30, 30, 90.
    V6  drives R4, 45 s late. Reports R1 and startTime 10:00:00, so the id is
        in force and the startTime agrees, and it looks trusted. R4 fits to 45 s
        and R1 to 3,645 s, so the run is a misfit and is matched to R4.
        R4 delays 45, 45, 45, 45, 45, 45, 105.

The bus day is the one in fixture_day.py, graded in the same session.
"""

import gzip
import json
from datetime import datetime, timedelta
from pathlib import Path

from fixture_day import _DOW, SERVICE_DATE, UTC, build_timetable, local, write_csv

RAIL = "LACMTA_Rail"
TRIPS = {
    "R1": (10, 0),
    "R2": (10, 20),
    "R3": (10, 40),
    "L1": (10, 30),
    "R4": (11, 0),
    "X1": (10, 20),
}


def station_lat(k: int) -> float:
    return 34.0 + 0.02 * (k - 1)


def scheduled(trip: str, k: int) -> datetime:
    hour, minute = TRIPS[trip]
    return local(18, hour, minute) + timedelta(minutes=5 * (k - 1))


def clock(trip: str, k: int) -> str:
    hour, minute = TRIPS[trip]
    total = hour * 60 + minute + 5 * (k - 1)
    return f"{total // 60}:{total % 60:02d}:00"


def build_rail_timetable(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    write_csv(
        directory / "calendar.txt",
        ["service_id", *_DOW, "start_date", "end_date"],
        [
            ["WK", *["1"] * 7, "20260101", "20261231"],
            ["LATER", *["1"] * 7, "20260901", "20261231"],
        ],
    )
    write_csv(directory / "calendar_dates.txt", ["service_id", "date", "exception_type"], [])
    write_csv(
        directory / "trips.txt",
        ["route_id", "service_id", "trip_id", "direction_id"],
        [
            ["802" if trip == "X1" else "801", "LATER" if trip == "L1" else "WK", trip, "0"]
            for trip in TRIPS
        ],
    )
    write_csv(
        directory / "stop_times.txt",
        ["trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence"],
        [[trip, clock(trip, k), clock(trip, k), f"S{k}", k] for trip in TRIPS for k in range(1, 8)],
    )
    write_csv(
        directory / "stops.txt",
        ["stop_id", "stop_name", "stop_lat", "stop_lon"],
        [[f"S{k}", f"Station {k}", station_lat(k), "-118.30"] for k in range(1, 8)],
    )
    return directory


def drive(
    vehicle: str, reported: str, start_time: str, base: str, late: int, route: str = "801"
) -> list[dict]:
    """The raw records of one vehicle driving trip `base`, `late` seconds late."""

    def record(k: int, status: str, moment: datetime) -> dict:
        return {
            "received_at": moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "agency": RAIL,
            "payload": {
                "vehicle": {
                    "trip": {
                        "tripId": reported,
                        "startDate": SERVICE_DATE,
                        "startTime": start_time,
                        "routeId": route,
                        "directionId": 0,
                    },
                    "position": {"latitude": station_lat(k), "longitude": -118.30},
                    "currentStopSequence": k,
                    "currentStatus": status,
                    "timestamp": str(int(moment.timestamp())),
                    "stopId": f"S{k}",
                    "vehicle": {"id": vehicle},
                }
            },
        }

    def at(k: int) -> datetime:
        return scheduled(base, k) + timedelta(seconds=late)

    out = [record(1, "STOPPED_AT", at(1) - timedelta(seconds=300))]
    out += [record(k, "STOPPED_AT", at(k)) for k in range(1, 7)]
    out += [
        record(7, "IN_TRANSIT_TO", at(7) - timedelta(seconds=60)),
        record(7, "IN_TRANSIT_TO", at(7) + timedelta(seconds=60)),
    ]
    return out


VEHICLES = [
    ("V1", "R1", "10:00:00", "R1", 30),
    ("V2", "R1", "10:20:00", "R2", 60),
    ("V3", "L1", "10:30:00", "R3", 90),
    ("V4", "R2", "10:05:00", "R1", 600),
    ("V5", "L1", "10:30:00", "X1", 30, "802"),
    ("V6", "R1", "10:00:00", "R4", 45),
]


def build_rail_raw(directory: Path) -> None:
    by_file: dict[Path, list[dict]] = {}
    for vehicle in VEHICLES:
        for row in drive(*vehicle):
            moment = datetime.fromtimestamp(int(row["payload"]["vehicle"]["timestamp"]), UTC)
            folder = directory / "vehicle_positions" / f"dt={moment:%Y-%m-%d}" / f"hh={moment:%H}"
            by_file.setdefault(folder / f"rail-{moment:%Y%m%dT%H}0000Z.jsonl.gz", []).append(row)
    for path, rows in by_file.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(path, "wt") as handle:
            for row in rows:
                handle.write(json.dumps(row) + "\n")


def run_rail_day(root: Path):
    """Grade the bus day and the rail day together, as `grade_day` orders the steps."""
    from fixture_day import REPORTS, build_raw

    from howlate_pipeline import BUS_AGENCY, arrivals

    raw = build_raw(root / "raw", REPORTS)
    build_rail_raw(raw)
    directories = {
        BUS_AGENCY: build_timetable(root / "gtfs_bus"),
        RAIL: build_rail_timetable(root / "gtfs_rail"),
    }
    con = arrivals.connect()
    arrivals.load_observations(con, arrivals.local_files(raw, SERVICE_DATE), SERVICE_DATE)
    arrivals.load_schedule(con, directories, SERVICE_DATE)
    arrivals.match_rail_runs(con, directories, SERVICE_DATE)
    arrivals.match(con, SERVICE_DATE)
    arrivals.interpolate(con)
    arrivals.trips(con)
    return con
