"""Which timetable a day is measured against, and how the raw files arrive.

Cloud Storage is replaced by small fakes that hold exactly what each test needs.
Nothing here touches the network.
"""

import io
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fixture_day import SERVICE_DATE, build_timetable

from howlate_pipeline import arrivals, gtfs


class FakeBlob:
    """A stored object: a name, a fetched_at stamp, and bytes to download.

    `fail_after` makes the first download write that many bytes and then die,
    the way a dropped connection does.
    """

    def __init__(
        self,
        name: str,
        fetched: datetime | None = None,
        data: bytes = b"",
        fail_after: int | None = None,
    ):
        self.name = name
        self.metadata = (
            {"fetched_at": fetched.isoformat().replace("+00:00", "Z")} if fetched else {}
        )
        self.updated = fetched or datetime(2026, 1, 1, tzinfo=UTC)
        self.data = data
        self.fail_after = fail_after
        self.written_to: list[Path] = []

    def download_to_filename(self, path) -> None:
        self.written_to.append(Path(path))
        if self.fail_after is not None:
            Path(path).write_bytes(self.data[: self.fail_after])
            self.fail_after = None
            raise ConnectionError("connection dropped mid-download")
        Path(path).write_bytes(self.data)


class FakeClient:
    def __init__(self, blobs: list[FakeBlob]):
        self.blobs = blobs

    def list_blobs(self, bucket: str, prefix: str):
        return [blob for blob in self.blobs if blob.name.startswith(prefix)]


def utc(month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, month, day, hour, minute, tzinfo=UTC)


# Three copies of the bus timetable, as the collector stores them.
AUG_10 = "gtfs/gtfs_bus-2026-08-10-aaaa.zip"
AUG_16 = "gtfs/gtfs_bus-2026-08-16-bbbb.zip"
AUG_19 = "gtfs/gtfs_bus-2026-08-19-cccc.zip"


def copies() -> FakeClient:
    return FakeClient([
        FakeBlob(AUG_10, utc(8, 10, 12)),
        FakeBlob(AUG_16, utc(8, 16, 12)),
        FakeBlob(AUG_19, utc(8, 19, 12)),
    ])  # fmt: skip


def test_the_newest_copy_in_force_comes_first():
    # The 18th's day starts 07:00 UTC on the 18th. The 16th's copy is the
    # newest that existed by then; the 19th's was fetched after and comes last.
    order = [blob.name for blob in gtfs.candidates(copies(), "gtfs_bus", "20260818")]
    assert order == [AUG_16, AUG_10, AUG_19]


def test_a_copy_fetched_during_the_day_is_not_in_force_for_it():
    # The 16th's day starts 07:00 UTC on the 16th, and that copy arrived at
    # noon. So the 16th is measured against the 10th's copy.
    order = [blob.name for blob in gtfs.candidates(copies(), "gtfs_bus", "20260816")]
    assert order == [AUG_10, AUG_16, AUG_19]


def test_in_force_means_before_the_local_day_starts_not_the_utc_day():
    # The collector fetches timetables at about 00:20 and 06:20 UTC. On the
    # 18th, 06:20 UTC is still the evening of the 17th in Los Angeles, so that
    # copy is in force; 07:30 UTC is after the day began at 07:00, so it is not.
    early = "gtfs/gtfs_bus-2026-08-18-dddd.zip"
    late = "gtfs/gtfs_bus-2026-08-18-eeee.zip"
    client = FakeClient([
        FakeBlob(AUG_16, utc(8, 16, 12)),
        FakeBlob(early, utc(8, 18, 6, 20)),
        FakeBlob(late, utc(8, 18, 7, 30)),
    ])  # fmt: skip
    order = [blob.name for blob in gtfs.candidates(client, "gtfs_bus", "20260818")]
    assert order == [early, AUG_16, late]


def test_in_force_uses_standard_time_in_winter():
    # On 2 December the day starts at 08:00 UTC, an hour later than in summer.
    # A copy fetched at 07:30 UTC is in force; one at 08:30 UTC is not.
    # The older copy is there so that a wrong cutoff changes the order:
    # counting from UTC midnight would put it first.
    older = "gtfs/gtfs_bus-2026-11-20-hhhh.zip"
    before = "gtfs/gtfs_bus-2026-12-02-ffff.zip"
    after = "gtfs/gtfs_bus-2026-12-02-gggg.zip"
    client = FakeClient([
        FakeBlob(older, utc(11, 20, 12)),
        FakeBlob(before, utc(12, 2, 7, 30)),
        FakeBlob(after, utc(12, 2, 8, 30)),
    ])  # fmt: skip
    order = [blob.name for blob in gtfs.candidates(client, "gtfs_bus", "20261202")]
    assert order == [before, older, after]


def test_no_timetable_at_all_stops_the_run():
    with pytest.raises(SystemExit):
        gtfs.candidates(FakeClient([]), "gtfs_bus", SERVICE_DATE)


def zipped(directory: Path) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        for path in directory.iterdir():
            bundle.write(path, path.name)
    return buffer.getvalue()


def test_a_copy_listing_no_service_is_skipped_for_an_older_one(tmp_path, monkeypatch):
    # A copy can be in force and still list nothing for the day, as one that
    # rolled its calendar forward does. The newest in-force copy here is empty,
    # so the older one has to be used instead of measuring nothing.
    empty = zipped(build_timetable(tmp_path / "empty", services=False))
    full = zipped(build_timetable(tmp_path / "full"))
    client = FakeClient([
        FakeBlob(AUG_10, utc(8, 10, 12), full),
        FakeBlob(AUG_16, utc(8, 16, 12), empty),
    ])  # fmt: skip
    monkeypatch.setattr(gtfs, "FEEDS", {"gtfs_bus": "LACMTA"})

    chosen = gtfs.prepare(client, SERVICE_DATE, tmp_path / "cache")
    assert chosen["LACMTA"].name == Path(AUG_10).stem


def test_running_out_of_copies_with_service_stops_the_run(tmp_path, monkeypatch):
    empty = zipped(build_timetable(tmp_path / "empty", services=False))
    client = FakeClient([FakeBlob(AUG_16, utc(8, 16, 12), empty)])
    monkeypatch.setattr(gtfs, "FEEDS", {"gtfs_bus": "LACMTA"})
    with pytest.raises(SystemExit):
        gtfs.prepare(client, SERVICE_DATE, tmp_path / "cache")


@pytest.mark.parametrize(
    "service_date, day",
    [
        ("20260818", (2026, 8, 18)),  # an ordinary day
        ("20261101", (2026, 11, 1)),  # clocks go back at 02:00
        ("20270314", (2027, 3, 14)),  # clocks go forward at 02:00
    ],
)
def test_gtfs_eight_am_is_eight_on_the_wall(service_date, day):
    # GTFS times count from noon minus twelve hours, not from midnight. On the
    # two clock-change days those differ by an hour, and counting from midnight
    # would shift every delay that day by 3,600 seconds.
    eight_am = datetime(*day, 8, tzinfo=ZoneInfo("America/Los_Angeles"))
    assert gtfs.day_base(service_date) + 8 * 3600 == eight_am.timestamp()


def test_an_interrupted_download_leaves_nothing_the_next_run_trusts(tmp_path):
    name = "vehicle_positions/dt=2026-08-18/hh=15/vehicle_positions-20260818T150000Z.jsonl.gz"
    blob = FakeBlob(name, data=b"0123456789" * 100, fail_after=300)
    client = FakeClient([blob])

    with pytest.raises(ConnectionError):
        arrivals.fetch_raw(client, SERVICE_DATE, tmp_path)
    assert not (tmp_path / name).exists()
    # A dropped connection raises, but a killed process does not get to clean
    # up. So the bytes must never have been written under the trusted name.
    assert all(path != tmp_path / name for path in blob.written_to)

    # The next run sees nothing usable, downloads again, and gets every byte.
    files = arrivals.fetch_raw(client, SERVICE_DATE, tmp_path)
    assert files == [str(tmp_path / name)]
    assert (tmp_path / name).read_bytes() == blob.data


def test_an_interrupted_timetable_download_is_not_trusted(tmp_path):
    full = zipped(build_timetable(tmp_path / "full"))
    blob = FakeBlob(AUG_16, utc(8, 16, 12), full, fail_after=len(full) // 2)
    cache = tmp_path / "cache"

    with pytest.raises(ConnectionError):
        gtfs.ensure_local(blob, cache)
    target = cache / Path(AUG_16).stem
    assert not (target / ".complete").exists()

    # The rerun downloads again and unpacks every file in full.
    directory = gtfs.ensure_local(blob, cache)
    assert (directory / ".complete").exists()
    assert (directory / "stop_times.txt").read_bytes() == (
        tmp_path / "full" / "stop_times.txt"
    ).read_bytes()


def test_an_interrupted_extraction_is_not_trusted(tmp_path, monkeypatch):
    # The download succeeds and the process dies while unpacking: stop_times.txt
    # is half written. No marker may exist, and the rerun must replace every
    # file rather than keep the half-written one.
    source = build_timetable(tmp_path / "full")
    blob = FakeBlob(AUG_16, utc(8, 16, 12), zipped(source))
    cache = tmp_path / "cache"

    real_extract = zipfile.ZipFile.extract

    def dies_mid_file(self, member, path=None, pwd=None):
        if member == "stop_times.txt":
            (Path(path) / member).write_bytes(b"trip_id,arriv")
            raise OSError("killed while unpacking")
        return real_extract(self, member, path, pwd)

    monkeypatch.setattr(zipfile.ZipFile, "extract", dies_mid_file)
    with pytest.raises(OSError):
        gtfs.ensure_local(blob, cache)
    assert not (cache / Path(AUG_16).stem / ".complete").exists()

    monkeypatch.undo()
    directory = gtfs.ensure_local(blob, cache)
    for path in source.iterdir():
        assert (directory / path.name).read_bytes() == path.read_bytes(), path.name
