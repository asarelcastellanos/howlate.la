"""The rail trip-match check, on a hand-built timetable and hand-built vehicles.

Route 801, direction 0, three trips with an 8 minute headway, as on the K line:

    TA leaves at 10:00, TB at 10:08, TC at 10:16
    each has 8 stops, S1 to S8, 3 minutes apart, and S1 is the origin

Route 802 has the same three trips as XA, XB and XC. For a vehicle on route 801
they are decoys that fit TB's times exactly and must never count as another trip
that fits, as are YB, on route 801 going the other way, and BUS, a bus trip on
the same stops.

A vehicle is built with `drive(vehicle, reported, drove)`: it reports the
trip_id `reported` and stops at S2 to S8 at the times `drove` scheduled, plus a
chosen delay.
"""

import math

import pytest
from fixture_day import run_day

from howlate_pipeline import report

RAIL = "LACMTA_Rail"
BASE = 1_800_000_000
TRIPS = {"TA": 0, "TB": 480, "TC": 960}
STOPS = 8


def timetable(con, trip, start, *, route="801", direction=0, agency=RAIL):
    for seq in range(1, STOPS + 1):
        con.execute(
            "INSERT INTO scheduled BY NAME SELECT ? AS agency, ? AS route_id, "
            "? AS direction_id, ? AS trip_id, ? AS stop_id, ? AS stop_sequence, "
            "? AS scheduled_arrival, ? AS is_origin",
            [
                agency,
                route,
                direction,
                trip,
                f"S{seq}",
                seq,
                BASE + start + 180 * (seq - 1),
                seq == 1,
            ],
        )


@pytest.fixture
def con(tmp_path):
    con = run_day(tmp_path)
    for trip, start in TRIPS.items():
        timetable(con, trip, start)
    for trip, start in {"XA": 0, "XB": 480, "XC": 960}.items():
        timetable(con, trip, start, route="802")
    timetable(con, "YB", TRIPS["TB"], direction=1)
    timetable(con, "BUS", TRIPS["TB"], agency="LACMTA")
    return con


def drive(con, vehicle, reported, drove, *, late=0, stops=range(2, STOPS + 1)):
    """A vehicle reporting `reported` while following `drove`'s times, `late` seconds late."""
    start = {**TRIPS, "XA": 0, "XB": 480, "XC": 960, "TZ": TRIPS["TB"]}[drove]
    con.execute(
        "INSERT INTO observations BY NAME SELECT ? AS agency, ? AS vehicle_id, "
        "? AS trip_id, range AS stop_sequence, 'STOPPED_AT' AS status, "
        "? + 180 * (range - 1) AS ts FROM range(?, ?)",
        [RAIL, vehicle, reported, BASE + start + late, stops.start, stops.stop],
    )


def total(con):
    """Runs judged and misfits, over every line."""
    lines = report.rail_misfits(con)
    return sum(runs for _, runs, _ in lines), sum(misfits for _, _, misfits in lines)


def test_a_run_on_the_trip_it_followed_is_judged_and_fits(con):
    drive(con, "V1", "TB", "TB", late=20)
    assert total(con) == (1, 0)


def test_a_run_that_followed_the_next_trip_is_a_misfit(con):
    # Reports TA, which left 8 minutes before TB, and stops at TB's times.
    drive(con, "V1", "TA", "TB", late=20)
    assert total(con) == (1, 1)


def test_a_run_a_second_headway_off_is_a_misfit(con):
    drive(con, "V1", "TA", "TC", late=-15)
    assert total(con) == (1, 1)


def test_a_run_that_is_late_and_fits_no_trip_is_not_a_misfit(con):
    # Reports TA and runs 4 minutes behind it. TB's times are 4 minutes ahead of
    # the run, which is a miss of 240 s and not the 60 s that counts as a fit.
    drive(con, "V1", "TA", "TA", late=240)
    assert total(con) == (1, 0)


def test_a_run_a_little_late_on_its_own_trip_is_not_a_misfit(con):
    # 3 minutes late on TA: its own miss is 180 s, but TB is 300 s away.
    drive(con, "V1", "TA", "TA", late=180)
    assert total(con) == (1, 0)


def test_a_run_with_too_few_timed_stops_is_not_judged(con):
    drive(con, "V1", "TA", "TB", stops=range(2, 2 + report.MIN_RUN_STOPS - 1))
    assert total(con) == (0, 0)
    drive(con, "V2", "TA", "TB", stops=range(2, 2 + report.MIN_RUN_STOPS))
    assert total(con) == (1, 1)


def test_a_trip_with_no_scheduled_stops_is_not_judged(con):
    # A later-start trip. explained_pct counts it, and there is no timetable to
    # fit it against.
    drive(con, "V1", "TZ", "TZ")
    assert total(con) == (0, 0)


def test_only_the_same_route_and_direction_count_as_another_trip(con):
    # XB, YB and BUS all match this run exactly. None is on route 801 going
    # direction 0 on the rail feed, so nothing fits it but its own trip.
    drive(con, "V1", "TA", "TB")
    con.execute("DELETE FROM scheduled WHERE trip_id = 'TB' AND agency = ?", [RAIL])
    assert total(con) == (1, 0)


def test_two_vehicles_on_one_trip_id_are_judged_apart(con):
    drive(con, "V1", "TB", "TB")
    drive(con, "V2", "TB", "TC")
    assert total(con) == (2, 1)


def test_a_run_counts_the_first_stop_report_not_the_last(con):
    # The vehicle sits at S2 until it leaves. Its first report is the arrival.
    drive(con, "V1", "TB", "TB")
    drive(con, "V1", "TB", "TB", late=300, stops=range(2, 3))
    assert total(con) == (1, 0)


def test_a_day_with_no_rail_runs_has_no_misfits(con):
    assert total(con) == (0, 0)
    assert report.summarise(con)["rail_misfit_pct"] == 0


def day_with(con, stale, *, line_runs=100):
    """`line_runs` runs on route 801, `stale` of them reporting a trip they did not follow.

    Route 802 has 100 runs that all report the trip they followed, so the whole
    rail share of misfits is half the share on route 801.
    """
    for i in range(line_runs - stale):
        drive(con, f"G{i}", "TB", "TB", late=i % 40)
    for i in range(stale):
        drive(con, f"S{i}", "TA", "TB")
    for i in range(100):
        drive(con, f"X{i}", "XB", "XB", late=i % 40)
    return report.checks(con, report.summarise(con))


def misfit_check(found):
    return next(check for check in found if check["name"] == "rail_misfit_pct")


LIMIT = report.EXPECTED["rail_misfit_pct"][1]


def test_the_check_passes_a_day_with_no_stale_trip_ids(con):
    check = misfit_check(day_with(con, 0))
    assert (check["value"], check["ok"]) == (0, True)


def test_the_check_fails_a_line_over_the_limit(con):
    stale = math.floor(LIMIT) + 1
    found = day_with(con, stale)
    check = misfit_check(found)
    assert check["value"] == pytest.approx(stale)
    assert check["ok"] is False
    assert report.document(con, "20260818")["ok"] is False


def test_the_check_passes_a_line_just_under_the_limit(con):
    assert misfit_check(day_with(con, math.ceil(LIMIT) - 1))["ok"] is True


def test_one_bad_line_fails_the_day_although_the_rail_share_stays_low(con):
    # Route 802's good runs halve the share of all rail runs, as the other
    # five lines did on 2026-11-13 when route 801 had 21.5% and all rail 5.3%.
    stale = math.floor(LIMIT) + 1
    found = day_with(con, stale)
    runs, misfits = total(con)
    assert (runs, misfits) == (200, stale)
    assert 100 * misfits / runs == pytest.approx(misfit_check(found)["value"] / 2)
    assert misfit_check(found)["ok"] is False


def test_a_line_with_few_runs_is_not_judged_however_many_are_stale(con):
    # Every one of route 801's 5 runs is stale, which is under MIN_LINE_RUNS.
    check = misfit_check(day_with(con, 5, line_runs=5))
    assert (check["value"], check["ok"]) == (0, True)
    assert total(con) == (105, 5)
