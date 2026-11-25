"""The claims of F0 in docs/spec/v0.6.0.md, C1 to C5, checked on small hand-built days."""

import csv
from pathlib import Path

import duckdb

from howlate_pipeline import arrivals, commute, gtfs

HOUR = 3600


def write_day(root: Path, day: str, rows: list[tuple]) -> None:
    """One graded day's arrivals file.

    A row is (agency, line, direction, trip, stop, sequence, scheduled, actual,
    source) with times in seconds after the service day's base, actual None when
    nothing was seen.
    """
    folder = root / f"service_date={day[:4]}-{day[4:6]}-{day[6:]}"
    folder.mkdir(parents=True)
    base = int(gtfs.day_base(day))
    con = duckdb.connect()
    con.execute(
        "CREATE TABLE a (service_date VARCHAR, agency VARCHAR, line VARCHAR, direction_id INTEGER, "
        "trip_id VARCHAR, stop_id VARCHAR, stop_sequence INTEGER, sched BIGINT, act BIGINT, "
        "source VARCHAR)"
    )
    con.executemany(
        "INSERT INTO a VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (day, agency, line, direction, trip, stop, seq, base + sched,
             None if act is None else base + act, source)
            for agency, line, direction, trip, stop, seq, sched, act, source in rows
        ],
    )  # fmt: skip
    con.execute(
        "COPY (SELECT service_date, agency, line, direction_id, trip_id, stop_id, stop_sequence, "
        "to_timestamp(sched) AS scheduled_time, to_timestamp(act) AS actual_time, source FROM a) "
        f"TO '{folder / 'part-0.parquet'}' (FORMAT parquet)"
    )


def loaded(root: Path, types: dict[str, str]):
    con = arrivals.connect()
    commute.load(con, [str(path) for path in sorted(root.glob("*/*.parquet"))], types)
    return con


def test_two_timetable_versions_with_a_weekday_742_departure_make_one_pattern(tmp_path):
    seven_forty_two = 7 * HOUR + 42 * 60
    for day, trip in (("20261102", "OCT-100"), ("20261110", "NOV-900")):
        write_day(tmp_path, day, [
            ("LACMTA", "720", 0, trip, "A", 1, seven_forty_two, seven_forty_two + 60, "stopped_at"),
            ("LACMTA", "720", 0, trip, "B", 2, seven_forty_two + 600, seven_forty_two + 660, "stopped_at"),
        ])  # fmt: skip
    con = loaded(tmp_path, {"20261102": "weekday", "20261110": "weekday"})
    assert commute.patterns(con) == [("720", 0, "weekday", 27720)]
    file = commute.route_file(con, "720", 0, "weekday", ["20261102", "20261110"])
    assert [(start, days) for start, days, _, _, _ in file["patterns"]] == [(27720, [0, 1])]
    assert file["patterns"][0][4] == [0, 60]


def write_timetable(directory: Path) -> Path:
    directory.mkdir(parents=True)

    def table(name: str, header: list[str], rows: list[list]) -> None:
        with (directory / name).open("w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(header)
            writer.writerows(rows)

    week = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    table("calendar.txt", ["service_id", *week, "start_date", "end_date"], [
        ["WK", 1, 1, 1, 1, 1, 0, 0, "20260101", "20261231"],
        ["SA", 0, 0, 0, 0, 0, 1, 0, "20260101", "20261231"],
        ["SU", 0, 0, 0, 0, 0, 0, 1, "20260101", "20261231"],
    ])  # fmt: skip
    table("calendar_dates.txt", ["service_id", "date", "exception_type"], [
        ["WK", "20261126", 2],
        ["SU", "20261126", 1],
    ])  # fmt: skip
    table("trips.txt", ["route_id", "service_id", "trip_id", "direction_id"], [
        ["720-1", "WK", "T1", 0],
        ["720-1", "SA", "T2", 0],
        ["720-1", "SU", "T3", 0],
    ])  # fmt: skip
    return directory


def test_each_date_takes_the_day_type_its_timetable_ran(tmp_path):
    timetable = write_timetable(tmp_path / "gtfs_bus")
    days = ["20261124", "20261128", "20261129", "20261126"]
    assert [commute.day_type(timetable, day) for day in days] == [
        "weekday",
        "saturday",
        "sunday",
        "sunday",
    ]


def test_a_trip_past_midnight_stays_with_the_day_it_started(tmp_path):
    start = 23 * HOUR + 50 * 60
    write_day(tmp_path, "20261120", [
        ("LACMTA", "720", 0, "LATE", "A", 1, start, start, "stopped_at"),
        ("LACMTA", "720", 0, "LATE", "B", 2, start + 900, start + 900, "stopped_at"),
        ("LACMTA", "720", 0, "LATE", "C", 3, start + 1800, start + 1800, "stopped_at"),
    ])  # fmt: skip
    con = loaded(tmp_path, {"20261120": "weekday", "20261121": "saturday"})
    assert commute.patterns(con) == [("720", 0, "weekday", 85800)]
    assert con.execute("SELECT count(*) FROM m WHERE daytype = 'weekday'").fetchone() == (3,)
    assert con.execute("SELECT count(*) FROM m WHERE daytype = 'saturday'").fetchone() == (0,)


def test_only_measured_bus_rows_are_kept(tmp_path):
    t = 8 * HOUR
    write_day(tmp_path, "20261102", [
        ("LACMTA", "720", 0, "B1", "A", 1, t, t + 30, "stopped_at"),
        ("LACMTA", "720", 0, "B1", "B", 2, t + 300, t + 330, "approach"),
        ("LACMTA", "720", 0, "B1", "C", 3, t + 600, t + 640, "interpolated"),
        ("LACMTA", "720", 0, "B1", "D", 4, t + 900, None, "none"),
        ("LACMTA_Rail", "801", 0, "R1", "X", 1, t, t + 20, "stopped_at"),
    ])  # fmt: skip
    con = loaded(tmp_path, {"20261102": "weekday"})
    assert con.execute("SELECT stop_id FROM m ORDER BY stop_sequence").fetchall() == [
        ("A",),
        ("B",),
    ]


def test_the_window_holds_the_56_days_ending_with_the_latest_graded_day(tmp_path):
    for day in ("20260928", "20260929", "20261123"):
        write_day(tmp_path, day, [("LACMTA", "720", 0, "T", "A", 1, 0, 0, "stopped_at")])
    assert commute.graded_days(tmp_path, "20261123") == ["20260929", "20261123"]
    assert [Path(file).parent.name for file in commute.window_files(tmp_path, "20261123")] == [
        "service_date=2026-09-29",
        "service_date=2026-11-23",
    ]
