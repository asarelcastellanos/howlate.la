"""The on-time share, the all-day numbers and network.json, each against a query of its own.

On time is 60 s early to 300 s late, both ends included (Metro's published
standard, see the constants in aggregate.py). The expected numbers below come
from a query written here over the arrival rows, never from aggregate's SQL, so
a mistake in one is not repeated in the other.
"""

import json
from collections import namedtuple

import pytest
import test_write
from test_site_files import fixture

from howlate_pipeline import DERIVED_BUCKET, aggregate

ZONE = "timezone('America/Los_Angeles', scheduled_time)"
HOUR = f"CAST((date_part('isodow', {ZONE}) - 1) * 24 + date_part('hour', {ZONE}) AS INTEGER)"

# Each line holds the fixture's five non-origin rows once per delay. The delays
# sit on both sides of both edges, so a window that is off by one second moves a
# share by at least 1 row in 40. Line 801 is rail, so the modes differ.
SERIES = {
    ("LACMTA", "720"): [-400, -61, -60, 0, 120, 300, 301, 900],
    ("LACMTA", "754"): [-61, -60, 60, 61, 299, 300, 301],
    ("LACMTA_Rail", "801"): [-60, -60, 300, 300, 301, -61],
}

Stats = namedtuple("Stats", "sched n ok late med p90")


def read(out, name):
    return json.loads((out / name).read_text())


def find(node, key):
    """Every value stored under `key`, at any depth."""
    if isinstance(node, dict):
        for name, value in node.items():
            if name == key:
                yield value
            yield from find(value, key)
    elif isinstance(node, list):
        for value in node:
            yield from find(value, key)


def build_three_lines(root):
    """The fixture day as three lines, built into `root`. Returns the connection and site."""
    con, catalogue, span = fixture(root)
    copies = [
        f"SELECT * REPLACE ('{agency}' AS agency, '{line}' AS line, {delay} AS delay_seconds) "
        "FROM base"
        for (agency, line), delays in SERIES.items()
        for delay in delays
    ]
    con.execute("CREATE OR REPLACE VIEW a AS " + " UNION ALL ".join(copies))
    catalogue["lines"][("LACMTA_Rail", "801")] = {
        "label": "Metro A Line",
        "via": "",
        "mode": "rail",
    }
    aggregate.build(con, catalogue, root / "site", *span)
    return con, root / "site"


def expect(con, where, keys=()):
    """Delay numbers per group, from the arrival rows by a query of this test's own."""
    select = "".join(f"{key}, " for key in keys)
    group = f"GROUP BY {', '.join(keys)}" if keys else ""
    rows = con.execute(f"""
        SELECT {select}
               count(*), count(delay_seconds),
               sum(CAST(delay_seconds BETWEEN -60 AND 300 AS INTEGER)),
               sum(CAST(delay_seconds > 300 AS INTEGER)),
               CAST(round(median(delay_seconds)) AS INTEGER),
               CAST(round(quantile_cont(delay_seconds, 0.9)) AS INTEGER)
        FROM a WHERE NOT is_origin AND {where} {group}
        HAVING count(delay_seconds) > 0
    """).fetchall()
    return {tuple(row[: len(keys)]): Stats(*row[len(keys) :]) for row in rows}


def assert_matches(actual, stats):
    assert actual["n"] == stats.n
    assert actual["med"] == stats.med
    assert actual["p90"] == stats.p90
    # Rounded to one decimal, so the figure is within 0.05 of the exact share.
    assert actual["pct5"] == pytest.approx(100 * stats.late / stats.n, abs=0.051)
    assert actual["ontime"] == pytest.approx(100 * stats.ok / stats.n, abs=0.051)


@pytest.fixture(scope="module")
def three(tmp_path_factory):
    return build_three_lines(tmp_path_factory.mktemp("three"))


@pytest.mark.parametrize(("delay", "share"), [(-61, 0.0), (-60, 100.0), (300, 100.0), (301, 0.0)])
def test_the_window_is_60_s_early_to_300_s_late_at_every_level(tmp_path, delay, share):
    """61 s early is early, 60 s early is on time, 300 s late is on time, 301 s late is late."""
    con, catalogue, span = fixture(tmp_path)
    con.execute(
        f"CREATE OR REPLACE VIEW a AS SELECT * REPLACE ({delay} AS delay_seconds) FROM base"
    )
    out = tmp_path / "site"
    aggregate.build(con, catalogue, out, *span)

    assert read(out, "index.json")["lines"][0]["ontime"] == share
    for direction in read(out, "lines/720.json")["directions"]:
        assert direction["all"]["ontime"] == share
        assert {hour["ontime"] for hour in direction["profile"]} == {share}
        for stop in direction["stops"]:
            assert stop["all"]["ontime"] == share
            assert stop["cells"]
    assert read(out, "network.json")["network"]["all"]["ontime"] == share


def test_one_delay_at_each_edge_gives_the_share_by_hand(tmp_path):
    """B is 61 s early, C 60 s early, F 300 s late and D 301 s late. H is never measured."""
    con, catalogue, span = fixture(tmp_path)
    con.execute("""
        CREATE OR REPLACE VIEW a AS
        SELECT * REPLACE (CASE stop_id WHEN 'B' THEN -61 WHEN 'C' THEN -60
                                       WHEN 'F' THEN 300 WHEN 'D' THEN 301 END AS delay_seconds)
        FROM base
    """)
    out = tmp_path / "site"
    aggregate.build(con, catalogue, out, *span)

    entry = read(out, "index.json")["lines"][0]
    assert (entry["n"], entry["ontime"]) == (4, 50.0)
    (direction,) = read(out, "lines/720.json")["directions"]
    assert (direction["all"]["n"], direction["all"]["ontime"]) == (4, 50.0)
    # Tuesday 08:00 holds B, C and D and Wednesday 01:00 holds F.
    assert {hour["h"]: (hour["n"], hour["ontime"]) for hour in direction["profile"]} == {
        32: (3, 33.3),
        49: (1, 100.0),
    }
    stops = {stop["id"]: stop for stop in direction["stops"]}
    assert {name: stop["all"]["ontime"] for name, stop in stops.items()} == {
        "B": 0.0,
        "C": 100.0,
        "D": 0.0,
        "F": 100.0,
    }
    assert [cell["d"] for cell in stops["B"]["cells"]] == ["wk-am"]


def test_the_size_cuts_hold_in_every_line_file(three):
    """Cells carry no ontime and a stop's all carries no n. Both cost size and add nothing."""
    _, out = three
    for line in ("720", "754", "801"):
        for direction in read(out, f"lines/{line}.json")["directions"]:
            assert set(direction["all"]) == {"n", "med", "p90", "pct5", "ontime"}
            for stop in direction["stops"]:
                assert set(stop["all"]) == {"med", "p90", "pct5", "ontime"}
                for cell in stop["cells"]:
                    assert set(cell) == {"d", "n", "sched", "med", "p90", "pct5"}


def test_a_stop_with_nothing_measured_has_an_all_object_of_nulls(tmp_path):
    """Stop D never reported. It stays in the file with its scheduled count, and no number."""
    con, catalogue, span = fixture(tmp_path)
    out = tmp_path / "site"
    aggregate.build(con, catalogue, out, *span)
    stops = {
        stop["id"]: stop
        for direction in read(out, "lines/720.json")["directions"]
        for stop in direction["stops"]
    }
    assert stops["D"]["n"] == 0
    assert stops["D"]["all"] == {"med": None, "p90": None, "pct5": None, "ontime": None}
    assert stops["B"]["n"] == 1


@pytest.mark.parametrize("line", ["720", "754", "801"])
def test_line_numbers_equal_a_query_on_the_arrival_rows(three, line):
    con, out = three
    where = f"line = '{line}'"
    document = read(out, f"lines/{line}.json")

    (total,) = expect(con, where).values()
    entry = next(row for row in read(out, "index.json")["lines"] if row["line"] == line)
    assert_matches(entry, total)
    assert entry["sched"] == total.sched

    by_direction = expect(con, where, ["direction_id"])
    assert [d["id"] for d in document["directions"]] == sorted(k[0] for k in by_direction)
    assert sum(d["all"]["n"] for d in document["directions"]) == total.n
    for direction in document["directions"]:
        assert_matches(direction["all"], by_direction[(direction["id"],)])

        by_hour = expect(con, where, ["direction_id", HOUR])
        hours = {k[1]: v for k, v in by_hour.items() if k[0] == direction["id"]}
        assert [h["h"] for h in direction["profile"]] == sorted(hours)
        for hour in direction["profile"]:
            assert_matches(hour, hours[hour["h"]])
            assert hour["sched"] == hours[hour["h"]].sched

        by_stop = expect(con, where, ["direction_id", "stop_id"])
        for stop in direction["stops"]:
            # A stop's all carries no count, because stop["n"] is the same number.
            assert_matches({**stop["all"], "n": stop["n"]}, by_stop[(direction["id"], stop["id"])])


def test_network_equals_a_query_on_the_arrival_rows_and_the_modes_add_up(three):
    con, out = three
    network = read(out, "network.json")
    scopes = {"network": "TRUE", "bus": "agency = 'LACMTA'", "rail": "agency = 'LACMTA_Rail'"}
    assert set(network) == set(scopes)

    for name, where in scopes.items():
        (total,) = expect(con, where).values()
        assert_matches(network[name]["all"], total)
        hours = {k[0]: v for k, v in expect(con, where, [HOUR]).items()}
        profile = network[name]["profile"]
        assert [h["h"] for h in profile] == sorted(hours)
        assert len(profile) <= 168
        for hour in profile:
            assert_matches(hour, hours[hour["h"]])
            assert hour["sched"] == hours[hour["h"]].sched

    assert network["rail"]["all"]["n"] > 0
    assert (
        network["bus"]["all"]["n"] + network["rail"]["all"]["n"] == network["network"]["all"]["n"]
    )
    for hour in network["network"]["profile"]:
        parts = [
            next((h["n"] for h in network[mode]["profile"] if h["h"] == hour["h"]), 0)
            for mode in ("bus", "rail")
        ]
        assert sum(parts) == hour["n"]


def test_a_mode_with_no_measured_arrival_is_empty_not_missing(tmp_path):
    """The fixture is all bus, so rail has no arrivals and must still be there."""
    con, catalogue, span = fixture(tmp_path)
    out = tmp_path / "site"
    aggregate.build(con, catalogue, out, *span)
    rail = read(out, "network.json")["rail"]
    assert rail == {
        "all": {"n": 0, "med": None, "p90": None, "pct5": None, "ontime": None},
        "profile": [],
    }
    bus = read(out, "network.json")["bus"]
    assert bus["all"]["n"] == read(out, "network.json")["network"]["all"]["n"] == 3


def test_the_pointer_counts_network_json(tmp_path):
    con, catalogue, span = fixture(tmp_path)
    out, client = tmp_path / "site", test_write.FakeClient([])
    _, names = aggregate.build(con, catalogue, out, *span)
    count, _ = aggregate.upload(client, out, names, run="20261116T130000Z")

    _, files = test_write.published(client)
    pointer = json.loads(client.store[(DERIVED_BUCKET, aggregate.POINTER)])
    assert "network.json" in names
    assert "network.json" in files
    assert count == pointer["files"] == len(files) == len(names) == 4
