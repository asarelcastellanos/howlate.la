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

    def download_to_filename(self, path) -> None:
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


def utc(month: int, day: int, hour: int) -> datetime:
    return datetime(2026, month, day, hour, tzinfo=UTC)


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

    # The next run sees nothing usable, downloads again, and gets every byte.
    files = arrivals.fetch_raw(client, SERVICE_DATE, tmp_path)
    assert files == [str(tmp_path / name)]
    assert (tmp_path / name).read_bytes() == blob.data
