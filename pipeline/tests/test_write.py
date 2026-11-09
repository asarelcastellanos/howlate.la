"""Writing a day: where it goes, what it replaces, and what reads it back.

A rerun must replace one day and nothing else, locally and in the bucket, and
the summary step must never read two layout versions of the same day.
"""

from pathlib import Path

import duckdb
import pytest
from fixture_day import SERVICE_DATE, run_day

from howlate_pipeline import aggregate, arrivals, report


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


def test_a_rerun_replaces_only_that_day_with_identical_rows(tmp_path):
    out = tmp_path / "out"
    other = out / "arrivals/v2/service_date=2026-08-17"
    other.mkdir(parents=True)
    (other / "part-0.parquet").write_bytes(b"another day, untouched")
    stale = out / "arrivals/v2/service_date=2026-08-18/part-1.parquet"
    stale.parent.mkdir(parents=True)
    stale.write_bytes(b"left over from a run that wrote two files")

    first = table(arrivals.write(run_day(tmp_path / "a"), out, SERVICE_DATE)["arrivals"])
    second = table(arrivals.write(run_day(tmp_path / "b"), out, SERVICE_DATE)["arrivals"])

    assert first == second
    assert not stale.exists()
    assert (other / "part-0.parquet").read_bytes() == b"another day, untouched"


class FakeBlob:
    def __init__(self, name: str, store: dict):
        self.name, self.store = name, store

    def delete(self) -> None:
        del self.store[self.name]

    def upload_from_filename(self, path, content_type=None) -> None:
        self.store[self.name] = Path(path).read_bytes()


class FakeBucket:
    def __init__(self, store: dict):
        self.store = store

    def blob(self, name: str) -> FakeBlob:
        return FakeBlob(name, self.store)


class FakeClient:
    def __init__(self, names: list[str]):
        self.store = dict.fromkeys(names, b"old")

    def bucket(self, name: str) -> FakeBucket:
        return FakeBucket(self.store)

    def list_blobs(self, bucket: str, prefix: str):
        return [FakeBlob(name, self.store) for name in list(self.store) if name.startswith(prefix)]


def test_an_upload_replaces_only_that_day_in_the_bucket(tmp_path):
    client = FakeClient([
        "arrivals/v2/service_date=2026-08-18/part-0.parquet",
        "arrivals/v2/service_date=2026-08-18/part-1.parquet",  # stale extra
        "arrivals/v2/service_date=2026-08-19/part-0.parquet",  # another day
        "arrivals/service_date=2026-08-18/part-0.parquet",  # v1, left alone
    ])  # fmt: skip
    written = arrivals.write(run_day(tmp_path / "day"), tmp_path / "out", SERVICE_DATE)
    arrivals.upload(client, written, SERVICE_DATE)

    assert sorted(client.store) == [
        "arrivals/service_date=2026-08-18/part-0.parquet",
        "arrivals/v2/service_date=2026-08-18/part-0.parquet",
        "arrivals/v2/service_date=2026-08-19/part-0.parquet",
        "trips/v2/service_date=2026-08-18/part-0.parquet",
    ]
    assert client.store["arrivals/v2/service_date=2026-08-19/part-0.parquet"] == b"old"
    assert client.store["arrivals/service_date=2026-08-18/part-0.parquet"] == b"old"


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


def test_the_report_checks_the_new_columns(day, capsys):
    stats = report.summarise(day)
    assert stats["vehicle_known"] == 100
    # T1 and T2 were seen and T3 was not.
    assert stats["trips_seen"] == pytest.approx(200 / 3)

    day.execute("UPDATE arrivals SET vehicle_id = NULL")
    assert report.summarise(day)["vehicle_known"] == 0
    report.show(day, SERVICE_DATE)
    lines = capsys.readouterr().out.splitlines()
    assert any(line.lstrip().startswith("CHECK") and "naming a vehicle" in line for line in lines)
