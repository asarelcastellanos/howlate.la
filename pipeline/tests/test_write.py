"""Writing a day: where it goes, what it replaces, and what reads it back.

A rerun must replace one day and nothing else, locally and in the bucket, and
the summary step must never read two layout versions of the same day.
"""

import json
from pathlib import Path

import duckdb
import pytest
from fixture_day import SERVICE_DATE, run_day
from google.api_core.exceptions import NotFound, PreconditionFailed

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


class Store(dict):
    """Objects keyed by (bucket, name), with a generation per write as GCS keeps."""

    def __init__(self, *args):
        super().__init__(*args)
        self.generations = dict.fromkeys(self, 1)
        self.after_get = None  # run once after get_blob, as another writer would

    def write(self, key, data: bytes) -> None:
        self[key] = data
        self.generations[key] = self.generations.get(key, 0) + 1


class FakeBlob:
    def __init__(self, bucket: str, name: str, store: Store):
        self.bucket_name, self.name, self.store = bucket, name, store
        self.generation = store.generations.get((bucket, name))

    def delete(self) -> None:
        del self.store[(self.bucket_name, self.name)]
        del self.store.generations[(self.bucket_name, self.name)]

    def upload_from_filename(self, path, content_type=None) -> None:
        self.store.write((self.bucket_name, self.name), Path(path).read_bytes())
        UPLOADS.append((self.name, content_type))

    def upload_from_string(self, data: str, content_type=None, if_generation_match=None) -> None:
        key = (self.bucket_name, self.name)
        if if_generation_match is not None and self.store.generations.get(key, 0) != (
            if_generation_match
        ):
            raise PreconditionFailed("generation changed")
        self.store.write(key, data.encode())

    def download_as_text(self, if_generation_match=None) -> str:
        # The real client reads the generation get_blob saw, which is gone
        # once the object is overwritten, so a stale read is a 404.
        key = (self.bucket_name, self.name)
        if if_generation_match is not None and self.store.generations[key] != if_generation_match:
            raise NotFound("that generation no longer exists")
        return self.store[key].decode()


UPLOADS: list[tuple[str, str]] = []


class FakeBucket:
    def __init__(self, name: str, store: dict):
        self.name, self.store = name, store

    def blob(self, name: str) -> FakeBlob:
        return FakeBlob(self.name, name, self.store)

    def get_blob(self, name: str) -> FakeBlob | None:
        if (self.name, name) not in self.store:
            return None
        found = FakeBlob(self.name, name, self.store)
        if self.store.after_get:
            cut_in, self.store.after_get = self.store.after_get, None
            cut_in()
        return found


class FakeClient:
    """Both buckets, keyed by (bucket, name), so writing to the wrong one shows."""

    def __init__(self, objects: list[tuple[str, str]]):
        self.store = Store(dict.fromkeys(objects, b"old"))

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


def test_the_report_goes_up_last_as_json(tmp_path):
    con = run_day(tmp_path / "day")
    out = tmp_path / "out"
    written = arrivals.write(con, out, SERVICE_DATE)
    written["reports"] = report.save(
        report.document(con, SERVICE_DATE),
        out / arrivals.partition("reports", SERVICE_DATE) / "report.json",
    )
    UPLOADS.clear()
    arrivals.upload(FakeClient([]), written, SERVICE_DATE)
    assert UPLOADS == [
        ("arrivals/v2/service_date=2026-08-18/part-0.parquet", "application/vnd.apache.parquet"),
        ("trips/v2/service_date=2026-08-18/part-0.parquet", "application/vnd.apache.parquet"),
        ("reports/v2/service_date=2026-08-18/report.json", "application/json"),
    ]


class FailsOn(FakeClient):
    """A bucket whose upload of one table dies partway, as a reclaimed VM would."""

    def __init__(self, objects, dies_on: str):
        super().__init__(objects)
        self.dies_on = dies_on

    def bucket(self, name: str) -> FakeBucket:
        client = self

        class Dying(FakeBucket):
            def blob(self, blob_name: str) -> FakeBlob:
                if client.dies_on in blob_name:
                    raise ConnectionError("killed mid-upload")
                return FakeBlob(self.name, blob_name, self.store)

        return Dying(name, self.store)


def test_a_regrade_that_dies_partway_leaves_no_report(tmp_path):
    # The day was graded before, so its report is in the bucket. The regrade
    # replaces arrivals and then dies on trips. The old report must be gone,
    # or every later run would skip a day whose tables no longer match it.
    day = [
        (DERIVED_BUCKET, "arrivals/v2/service_date=2026-08-18/part-0.parquet"),
        (DERIVED_BUCKET, "trips/v2/service_date=2026-08-18/part-0.parquet"),
        (DERIVED_BUCKET, "reports/v2/service_date=2026-08-18/report.json"),
    ]
    client = FailsOn(day, dies_on="trips/")
    con = run_day(tmp_path / "day")
    out = tmp_path / "out"
    written = arrivals.write(con, out, SERVICE_DATE)
    written["reports"] = report.save(
        report.document(con, SERVICE_DATE),
        out / arrivals.partition("reports", SERVICE_DATE) / "report.json",
    )
    with pytest.raises(ConnectionError):
        arrivals.upload(client, written, SERVICE_DATE)
    assert not any(name.startswith("reports/") for _, name in client.store)


def site(tmp_path, lines=("720", "754"), days=2):
    """A small built site: an index, a status file and one file per line."""
    out = tmp_path / "site"
    (out / "lines").mkdir(parents=True)
    (out / "index.json").write_text(f'{{"days": {days}}}')
    (out / "status.json").write_text(f'{{"days": {days}}}')
    for line in lines:
        (out / "lines" / f"{line}.json").write_text(f'{{"line": "{line}", "days": {days}}}')
    return out


def published(client):
    """The run site/current.json names, and its files with their contents."""
    pointer = json.loads(client.store[(DERIVED_BUCKET, "site/current.json")])
    files = {
        name.removeprefix(pointer["prefix"]): data
        for (bucket, name), data in client.store.items()
        if bucket == DERIVED_BUCKET and name.startswith(pointer["prefix"])
    }
    return pointer["run"], files


def pointer(client):
    return json.loads(client.store[(DERIVED_BUCKET, "site/current.json")])["run"]


def runs_in(client):
    return {name.split("/")[2] for _, name in client.store if name.startswith("site/runs/")}


def runs(*names):
    return [(DERIVED_BUCKET, f"site/runs/{run}/index.json") for run in names]


def point(client, run, previous=()):
    """Set site/current.json as an earlier publish would have."""
    record = {"run": run, "prefix": f"site/runs/{run}/", "files": 1, "previous": list(previous)}
    client.store.write((DERIVED_BUCKET, "site/current.json"), json.dumps(record).encode())


def test_publishing_writes_a_run_then_points_at_it(tmp_path):
    # The flat layout from before runs existed is cleared out.
    old = [(DERIVED_BUCKET, "site/index.json"), (DERIVED_BUCKET, "site/lines/1.json")]
    client = FakeClient(old)
    count, where = aggregate.upload(client, site(tmp_path), run="20261110T130000Z")
    assert (count, where) == (4, f"gs://{DERIVED_BUCKET}/site/runs/20261110T130000Z/")
    run, files = published(client)
    assert run == "20261110T130000Z"
    assert sorted(files) == [
        "index.json", "lines/720.json", "lines/754.json", "status.json"
    ]  # fmt: skip
    assert not [key for key in old if key in client.store]


def test_a_publish_that_dies_partway_leaves_the_last_run_published(tmp_path):
    # Issue #87: a failed run must not leave a mix of old and new files. The
    # second build has different numbers, so any file of it that leaked into
    # the published run would show.
    client = FailsOn([], dies_on="lines/754.json")
    client.dies_on = "never"
    aggregate.upload(client, site(tmp_path / "a", days=2), run="20261110T130000Z")
    before = published(client)
    client.dies_on = "lines/754.json"
    with pytest.raises(ConnectionError):
        aggregate.upload(client, site(tmp_path / "b", days=3), run="20261111T130000Z")
    assert published(client) == before
    assert {json.loads(data)["days"] for data in before[1].values()} == {2}


def test_the_last_three_published_runs_and_any_newer_stay(tmp_path):
    client = FakeClient(runs("20261101T1", "20261102T1", "20261103T1", "20261104T1"))
    point(client, "20261104T1", previous=["20261103T1", "20261102T1"])
    # A run named after the one being published may still be uploading.
    client.store.write((DERIVED_BUCKET, "site/runs/20261106T1/index.json"), b"{}")
    aggregate.upload(client, site(tmp_path), run="20261105T1")
    assert runs_in(client) == {"20261103T1", "20261104T1", "20261105T1", "20261106T1"}


def test_runs_that_were_never_current_do_not_take_a_place(tmp_path):
    # 20261102 died partway and 20261103 lost a race to a newer run, so
    # neither was ever current. 20261101 was current a moment ago, and a
    # reader may still be copying it.
    client = FakeClient(runs("20261101T1", "20261102T1", "20261103T1"))
    point(client, "20261101T1")
    aggregate.upload(client, site(tmp_path), run="20261104T1")
    assert runs_in(client) == {"20261101T1", "20261104T1"}
    assert json.loads(client.store[(DERIVED_BUCKET, "site/current.json")])["previous"] == [
        "20261101T1"
    ]


def test_a_slower_older_run_does_not_move_the_pointer_back(tmp_path, capsys):
    client = FakeClient(runs("20261110T130020Z"))
    point(client, "20261110T130020Z")
    aggregate.upload(client, site(tmp_path), run="20261110T130000Z")
    assert pointer(client) == "20261110T130020Z"
    assert "already names 20261110T130020Z" in capsys.readouterr().out


def test_a_pointer_moved_before_it_is_written_is_read_again(tmp_path, monkeypatch):
    client = FakeClient(runs("20261110T120000Z"))
    point(client, "20261110T120000Z")
    write = FakeBlob.upload_from_string
    cut_in = []

    def another_run_publishes_first(self, data, content_type=None, if_generation_match=None):
        # Between this run reading the pointer and writing it, a newer run
        # publishes. The conditional write must fail and the pointer be read
        # again, not overwritten.
        if self.name == "site/current.json" and not cut_in:
            cut_in.append(True)
            point(client, "20261110T140000Z")
        write(self, data, content_type, if_generation_match)

    monkeypatch.setattr(FakeBlob, "upload_from_string", another_run_publishes_first)
    aggregate.upload(client, site(tmp_path), run="20261110T130000Z")
    assert cut_in
    assert pointer(client) == "20261110T140000Z"


def test_a_pointer_moved_before_it_is_read_is_read_again(tmp_path):
    # The other window: after get_blob, before the download.
    client = FakeClient(runs("20261110T120000Z"))
    point(client, "20261110T120000Z")
    client.store.after_get = lambda: point(client, "20261110T125000Z", ["20261110T120000Z"])
    aggregate.upload(client, site(tmp_path), run="20261110T130000Z")
    assert pointer(client) == "20261110T130000Z"


def test_a_pointer_write_that_landed_but_reported_failure_keeps_the_history(tmp_path, monkeypatch):
    # The client retries a write whose answer was lost; the retry finds the
    # generation moved, by this run's own write, and fails. Reading again must
    # not list this run as its own predecessor and push out the oldest run.
    client = FakeClient(runs("20261101T1", "20261102T1", "20261103T1"))
    point(client, "20261103T1", previous=["20261102T1", "20261101T1"])
    write = FakeBlob.upload_from_string
    lost = []

    def answer_lost(self, data, content_type=None, if_generation_match=None):
        write(self, data, content_type, if_generation_match)
        if self.name == "site/current.json" and not lost:
            lost.append(True)
            raise PreconditionFailed("retry found the generation moved")

    monkeypatch.setattr(FakeBlob, "upload_from_string", answer_lost)
    aggregate.upload(client, site(tmp_path), run="20261104T1")
    assert lost
    assert runs_in(client) == {"20261102T1", "20261103T1", "20261104T1"}


def test_two_runs_started_in_the_same_second_get_their_own_prefix(tmp_path):
    client = FakeClient([])
    _, first = aggregate.upload(client, site(tmp_path / "a"))
    _, second = aggregate.upload(client, site(tmp_path / "b"))
    assert first != second


def test_a_failed_delete_does_not_fail_the_publish(tmp_path, capsys, monkeypatch):
    client = FakeClient([(DERIVED_BUCKET, "site/index.json")])

    def stuck(self):
        raise ConnectionError("delete refused")

    monkeypatch.setattr(FakeBlob, "delete", stuck)
    aggregate.upload(client, site(tmp_path), run="20261110T130000Z")
    assert published(client)[0] == "20261110T130000Z"
    assert "could not delete" in capsys.readouterr().out


def test_a_failed_listing_does_not_fail_the_publish(tmp_path, capsys, monkeypatch):
    client = FakeClient([])

    def unreachable(bucket, prefix):
        raise ConnectionError("503")

    monkeypatch.setattr(client, "list_blobs", unreachable)
    aggregate.upload(client, site(tmp_path), run="20261110T130000Z")
    assert published(client)[0] == "20261110T130000Z"
    assert "could not prune" in capsys.readouterr().out
