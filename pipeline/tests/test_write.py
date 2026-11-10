"""Writing a day: where it goes, what it replaces, and what reads it back.

A rerun must replace one day and nothing else, locally and in the bucket, and
the summary step must never read two layout versions of the same day.
"""

from pathlib import Path

import duckdb
import pytest
from fixture_day import SERVICE_DATE, run_day

from howlate_pipeline import DERIVED_BUCKET, RAW_BUCKET, aggregate, arrivals, report


def table(path: Path) -> list[tuple]:
    # As text: DuckDB 1.x needs pytz to hand timestamps with a time zone to
    # Python, and pytz is not a dependency of the pipeline.
    return duckdb.sql(f"SELECT CAST(COLUMNS(*) AS VARCHAR) FROM read_parquet('{path}')").fetchall()


def test_a_day_writes_arrivals_and_trips_under_the_version(tmp_path):
    con = run_day(tmp_path / "day")
    written = arrivals.write(con, tmp_path / "out", SERVICE_DATE)

    assert written["arrivals"] == (
        tmp_path / "out/arrivals/v2/service_date=2026-08-18/part-0.parquet"
    )
    assert written["trips"] == tmp_path / "out/trips/v2/service_date=2026-08-18/part-0.parquet"
    assert len(table(written["arrivals"])) == 8
    assert len(table(written["trips"])) == 3

    columns = [name for name, *_ in duckdb.sql(
        f"DESCRIBE SELECT * FROM read_parquet('{written['arrivals']}')"
    ).fetchall()]  # fmt: skip
    assert {"vehicle_id", "departure_time"} <= set(columns)


def seed(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


@pytest.mark.parametrize("table_name", ["arrivals", "trips"])
def test_a_rerun_replaces_only_that_day_with_identical_rows(tmp_path, table_name):
    out = tmp_path / "out"
    other_day = seed(out / f"{table_name}/v2/service_date=2026-08-17/part-0.parquet", b"other")
    v1_day = seed(out / f"{table_name}/service_date=2026-08-18/part-0.parquet", b"v1")
    stale = seed(out / f"{table_name}/v2/service_date=2026-08-18/part-1.parquet", b"stale")

    first = table(arrivals.write(run_day(tmp_path / "a"), out, SERVICE_DATE)[table_name])
    second = table(arrivals.write(run_day(tmp_path / "b"), out, SERVICE_DATE)[table_name])

    assert first == second
    assert not stale.exists()
    assert other_day.read_bytes() == b"other"
    assert v1_day.read_bytes() == b"v1"


class FakeBlob:
    def __init__(self, bucket: str, name: str, store: dict):
        self.bucket_name, self.name, self.store = bucket, name, store

    def delete(self) -> None:
        del self.store[(self.bucket_name, self.name)]

    def upload_from_filename(self, path, content_type=None) -> None:
        self.store[(self.bucket_name, self.name)] = Path(path).read_bytes()


class FakeBucket:
    def __init__(self, name: str, store: dict):
        self.name, self.store = name, store

    def blob(self, name: str) -> FakeBlob:
        return FakeBlob(self.name, name, self.store)


class FakeClient:
    """Both buckets, keyed by (bucket, name), so writing to the wrong one shows."""

    def __init__(self, objects: list[tuple[str, str]]):
        self.store = dict.fromkeys(objects, b"old")

    def bucket(self, name: str) -> FakeBucket:
        return FakeBucket(name, self.store)

    def list_blobs(self, bucket: str, prefix: str):
        return [
            FakeBlob(b, name, self.store)
            for b, name in list(self.store)
            if b == bucket and name.startswith(prefix)
        ]


def test_an_upload_replaces_only_that_day_in_the_derived_bucket(tmp_path):
    derived, raw = DERIVED_BUCKET, RAW_BUCKET
    untouched = [
        (derived, "arrivals/v2/service_date=2026-08-19/part-0.parquet"),  # another day
        (derived, "trips/v2/service_date=2026-08-19/part-0.parquet"),
        (derived, "arrivals/service_date=2026-08-18/part-0.parquet"),  # v1
        (derived, "trips/service_date=2026-08-18/part-0.parquet"),
        # The raw bucket, under the very same prefix. Nothing here may touch it.
        (raw, "arrivals/v2/service_date=2026-08-18/part-0.parquet"),
        (raw, "trips/v2/service_date=2026-08-18/part-1.parquet"),
    ]
    replaced = [
        (derived, "arrivals/v2/service_date=2026-08-18/part-0.parquet"),
        (derived, "trips/v2/service_date=2026-08-18/part-0.parquet"),
    ]
    stale = [
        (derived, "arrivals/v2/service_date=2026-08-18/part-1.parquet"),
        (derived, "trips/v2/service_date=2026-08-18/part-1.parquet"),
    ]
    client = FakeClient(untouched + replaced + stale)
    written = arrivals.write(run_day(tmp_path / "day"), tmp_path / "out", SERVICE_DATE)
    arrivals.upload(client, written, SERVICE_DATE)

    assert sorted(client.store) == sorted(untouched + replaced)
    for key in untouched:
        assert client.store[key] == b"old", key
    for (_, name), table_name in zip(replaced, ["arrivals", "trips"], strict=True):
        assert client.store[(derived, name)] == written[table_name].read_bytes()


def test_the_summary_reads_one_version_and_v1_stays_readable(tmp_path):
    out = tmp_path / "out"
    arrivals.write(run_day(tmp_path / "day"), out, SERVICE_DATE)

    # A v1 partition of the same day, with the v1 columns, at the v1 path.
    v1 = out / "arrivals/service_date=2026-08-18/part-0.parquet"
    v1.parent.mkdir(parents=True)
    duckdb.sql(f"""
        COPY (SELECT * EXCLUDE (vehicle_id, departure_time)
              FROM read_parquet('{out}/arrivals/v2/service_date=2026-08-18/part-0.parquet'))
        TO '{v1}' (FORMAT parquet)
    """)
    assert len(table(v1)) == 8

    con = arrivals.connect()
    aggregate.load(con, out / "arrivals" / "v2")
    in_v2 = con.sql("SELECT count(*) FROM a").fetchall()[0][0]

    con = arrivals.connect()
    aggregate.load(con, out / "arrivals")  # the root, by mistake
    at_root = con.sql("SELECT count(*) FROM a").fetchall()[0][0]

    # Origins are excluded from the summary: T1, T2 and T3 each have one, so
    # 8 rows become 5. Pointed at the root, it reads only v1, not both.
    assert in_v2 == 5
    assert at_root == 5


@pytest.fixture
def day(tmp_path):
    return run_day(tmp_path)


def test_the_report_flags_absurd_delays(day, capsys):
    day.execute("UPDATE arrivals SET delay_seconds = 7200 WHERE delay_seconds IS NOT NULL")
    assert report.summarise(day)["absurd_pct"] == 100
    report.show(day, SERVICE_DATE)
    lines = capsys.readouterr().out.splitlines()
    assert any(line.lstrip().startswith("CHECK") and "beyond an hour" in line for line in lines)


def check_lines(day, capsys) -> list[str]:
    report.show(day, SERVICE_DATE)
    return [
        line for line in capsys.readouterr().out.splitlines() if line.lstrip().startswith("CHECK")
    ]


def test_the_report_checks_the_new_columns(day, capsys):
    stats = report.summarise(day)
    assert stats["vehicle_known"] == 100
    # T1 and T2 were seen and T3 was not: 67%, below the 90% floor.
    assert stats["trips_seen"] == pytest.approx(200 / 3)
    assert any("scheduled trips with any report" in line for line in check_lines(day, capsys))


def test_vehicle_known_counts_only_timed_arrivals(day, capsys):
    # Five timed arrivals. Name a vehicle on an untimed row, which must not
    # count, and blank one timed row's vehicle: 4 of 5 is 80%.
    day.execute("UPDATE arrivals SET vehicle_id = 'X' WHERE trip_id = 'T3' AND stop_sequence = 1")
    day.execute("UPDATE arrivals SET vehicle_id = NULL WHERE trip_id = 'T1' AND stop_sequence = 2")
    assert report.summarise(day)["vehicle_known"] == pytest.approx(80)
    assert any("naming a vehicle" in line for line in check_lines(day, capsys))
