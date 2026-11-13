"""Which timetable a day is measured against, and how the raw files arrive.

Cloud Storage is replaced by small fakes that hold exactly what each test needs.
Nothing here touches the network.
"""

import io
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fixture_day import SERVICE_DATE, build_raw, build_timetable, write_csv

from howlate_pipeline import __main__ as cli
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


def holding(directory: Path, trips: list[str]) -> bytes:
    """A zipped timetable running exactly these trips every day of 2026."""
    directory.mkdir(parents=True)
    write_csv(
        directory / "calendar.txt",
        ["service_id", *DAYS, "start_date", "end_date"],
        [["WK", *["1"] * 7, "20260101", "20261231"]],
    )
    write_csv(directory / "calendar_dates.txt", ["service_id", "date", "exception_type"], [])
    write_csv(
        directory / "trips.txt",
        ["route_id", "service_id", "trip_id"],
        [["720-13201", "WK", trip] for trip in trips],
    )
    return zipped(directory)


DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
BEFORE = "gtfs/gtfs_bus-2026-08-16-bbbb.zip"
DURING = "gtfs/gtfs_bus-2026-08-18-dddd.zip"
BOTH_FEEDS = {"gtfs_bus": "LACMTA", "gtfs_rail": "LACMTA_Rail"}


def reported(count: int) -> list[str]:
    return [f"R{n}" for n in range(count)]


def test_the_copy_holding_the_reported_trips_is_used_over_the_one_in_force(tmp_path, monkeypatch):
    # The 18th starts 07:00 UTC. BEFORE was in force then and holds none of the
    # trips the vehicles reported; DURING, fetched at 12:00 UTC, holds all.
    client = FakeClient([
        FakeBlob(BEFORE, utc(8, 16, 12), holding(tmp_path / "before", ["OLD1", "OLD2"])),
        FakeBlob(DURING, utc(8, 18, 12), holding(tmp_path / "during", reported(10))),
    ])  # fmt: skip
    monkeypatch.setattr(gtfs, "FEEDS", {"gtfs_bus": "LACMTA"})

    chosen = gtfs.prepare(client, "20260818", tmp_path / "cache", {"LACMTA": set(reported(10))})
    assert chosen["LACMTA"].name == Path(DURING).stem


def test_the_log_names_the_copy_its_match_rate_and_the_one_in_force(tmp_path, monkeypatch, capsys):
    client = FakeClient([
        FakeBlob(BEFORE, utc(8, 16, 12), holding(tmp_path / "before", reported(1))),
        FakeBlob(DURING, utc(8, 18, 12), holding(tmp_path / "during", reported(10))),
    ])  # fmt: skip
    monkeypatch.setattr(gtfs, "FEEDS", {"gtfs_bus": "LACMTA"})

    gtfs.prepare(client, "20260818", tmp_path / "cache", {"LACMTA": set(reported(10))})
    assert capsys.readouterr().out.splitlines() == [
        "  gtfs_bus: gtfs_bus-2026-08-18-dddd.zip, 1 services active on 20260818, "
        "100.0% of observed trips match (the copy in force at midnight: 10.0%)"
    ]


@pytest.mark.parametrize(
    "in_force_holds, later_holds, switches",
    [
        (200, 200, False),  # equal: the day already graded correctly
        (150, 150, False),
        (150, 151, False),  # one trip in 200 is exactly 0.5 points, which is not more
        (150, 152, True),  # 1.0 points
        (150, 100, False),  # a worse copy fetched later never wins
    ],
)
def test_a_later_copy_must_match_clearly_better_to_replace_the_one_in_force(
    tmp_path, monkeypatch, in_force_holds, later_holds, switches
):
    # Even the best copy misses a few reported trips (26 of 1,348 on 2026-10-14),
    # so a margin of half a point keeps a day that graded correctly from
    # flipping on a trip or two.
    client = FakeClient([
        FakeBlob(BEFORE, utc(8, 16, 12), holding(tmp_path / "a", reported(in_force_holds))),
        FakeBlob(DURING, utc(8, 18, 12), holding(tmp_path / "b", reported(later_holds))),
    ])  # fmt: skip
    monkeypatch.setattr(gtfs, "FEEDS", {"gtfs_bus": "LACMTA"})

    chosen = gtfs.prepare(client, "20260818", tmp_path / "cache", {"LACMTA": set(reported(200))})
    assert chosen["LACMTA"].name == Path(DURING if switches else BEFORE).stem


def test_among_later_copies_that_qualify_the_best_match_wins_and_ties_go_to_the_newest(
    tmp_path, monkeypatch
):
    noon = "gtfs/gtfs_bus-2026-08-18-1200.zip"
    best = "gtfs/gtfs_bus-2026-08-18-1500.zip"
    newest = "gtfs/gtfs_bus-2026-08-18-1800.zip"
    client = FakeClient([
        FakeBlob(BEFORE, utc(8, 16, 12), holding(tmp_path / "a", reported(10))),
        FakeBlob(noon, utc(8, 18, 12), holding(tmp_path / "b", reported(80))),
        FakeBlob(best, utc(8, 18, 15), holding(tmp_path / "c", reported(100))),
        FakeBlob(newest, utc(8, 18, 18), holding(tmp_path / "d", reported(100))),
    ])  # fmt: skip
    monkeypatch.setattr(gtfs, "FEEDS", {"gtfs_bus": "LACMTA"})

    chosen = gtfs.prepare(client, "20260818", tmp_path / "cache", {"LACMTA": set(reported(100))})
    assert chosen["LACMTA"].name == Path(newest).stem


def test_a_feed_with_no_reported_trips_keeps_the_copy_in_force(tmp_path, monkeypatch):
    # Only the bus reported anything. The rail copy fetched during the day holds
    # trips, but nothing says it describes the day better, so it is not used.
    rail_before = "gtfs/gtfs_rail-2026-08-16-bbbb.zip"
    rail_during = "gtfs/gtfs_rail-2026-08-18-dddd.zip"
    client = FakeClient([
        FakeBlob(BEFORE, utc(8, 16, 12), holding(tmp_path / "a", ["OLD"])),
        FakeBlob(DURING, utc(8, 18, 12), holding(tmp_path / "b", reported(10))),
        FakeBlob(rail_before, utc(8, 16, 12), holding(tmp_path / "c", ["OLD"])),
        FakeBlob(rail_during, utc(8, 18, 12), holding(tmp_path / "d", reported(10))),
    ])  # fmt: skip
    monkeypatch.setattr(gtfs, "FEEDS", BOTH_FEEDS)

    chosen = gtfs.prepare(client, "20260818", tmp_path / "cache", {"LACMTA": set(reported(10))})
    assert chosen["LACMTA"].name == Path(DURING).stem
    assert chosen["LACMTA_Rail"].name == Path(rail_before).stem


def test_without_reported_trips_every_feed_keeps_the_copy_in_force(tmp_path, monkeypatch, capsys):
    client = FakeClient([
        FakeBlob(BEFORE, utc(8, 16, 12), holding(tmp_path / "a", ["OLD"])),
        FakeBlob(DURING, utc(8, 18, 12), holding(tmp_path / "b", reported(10))),
    ])  # fmt: skip
    monkeypatch.setattr(gtfs, "FEEDS", {"gtfs_bus": "LACMTA"})

    for observed in (None, {}):
        chosen = gtfs.prepare(client, "20260818", tmp_path / "cache", observed)
        assert chosen["LACMTA"].name == Path(BEFORE).stem
    assert "match" not in capsys.readouterr().out


def test_the_log_names_the_earliest_copy_when_none_was_in_force_with_service(
    tmp_path, monkeypatch, capsys
):
    # Both copies were fetched during the 18th and nothing earlier exists, so the
    # baseline is the earliest of them, not a copy in force at midnight.
    first = "gtfs/gtfs_bus-2026-08-18-1200.zip"
    second = "gtfs/gtfs_bus-2026-08-18-1500.zip"
    client = FakeClient([
        FakeBlob(first, utc(8, 18, 12), holding(tmp_path / "a", reported(1))),
        FakeBlob(second, utc(8, 18, 15), holding(tmp_path / "b", reported(10))),
    ])  # fmt: skip
    monkeypatch.setattr(gtfs, "FEEDS", {"gtfs_bus": "LACMTA"})

    gtfs.prepare(client, "20260818", tmp_path / "cache", {"LACMTA": set(reported(10))})
    assert capsys.readouterr().out.splitlines() == [
        "  gtfs_bus: gtfs_bus-2026-08-18-1500.zip, 1 services active on 20260818, "
        "100.0% of observed trips match (the earliest copy with service: 10.0%)"
    ]


def test_a_copy_fetched_during_the_day_that_cannot_be_read_is_skipped(
    tmp_path, monkeypatch, capsys
):
    # DURING arrives without trips.txt. The copy in force is complete, so the day
    # is graded against it and the log says what was skipped.
    broken = tmp_path / "broken"
    holding(broken, reported(10))
    (broken / "trips.txt").unlink()
    client = FakeClient([
        FakeBlob(BEFORE, utc(8, 16, 12), holding(tmp_path / "before", reported(10))),
        FakeBlob(DURING, utc(8, 18, 12), zipped(broken)),
    ])  # fmt: skip
    monkeypatch.setattr(gtfs, "FEEDS", {"gtfs_bus": "LACMTA"})

    chosen = gtfs.prepare(client, "20260818", tmp_path / "cache", {"LACMTA": set(reported(10))})
    assert chosen["LACMTA"].name == Path(BEFORE).stem
    assert capsys.readouterr().out.splitlines() == [
        "  gtfs_bus: gtfs_bus-2026-08-18-dddd.zip could not be read (FileNotFoundError), skipped",
        "  gtfs_bus: gtfs_bus-2026-08-16-bbbb.zip, 1 services active on 20260818, "
        "100.0% of observed trips match (the copy in force at midnight: 100.0%)",
    ]


def test_an_older_copy_in_force_is_not_chosen_over_the_newest_one(tmp_path, monkeypatch):
    # AUG_10 matches all ten reported trips and BEFORE, the newest copy in force,
    # matches two. Only copies fetched during the day may replace the baseline,
    # so the better-matching older copy is never considered.
    client = FakeClient([
        FakeBlob(AUG_10, utc(8, 10, 12), holding(tmp_path / "a", reported(10))),
        FakeBlob(BEFORE, utc(8, 16, 12), holding(tmp_path / "b", reported(2))),
    ])  # fmt: skip
    monkeypatch.setattr(gtfs, "FEEDS", {"gtfs_bus": "LACMTA"})

    chosen = gtfs.prepare(client, "20260818", tmp_path / "cache", {"LACMTA": set(reported(10))})
    assert chosen["LACMTA"].name == Path(BEFORE).stem


def test_a_copy_fetched_between_local_midnight_and_the_day_base_is_in_force():
    # On 1 November, local midnight is 07:00 UTC (PDT) and day_base is 08:00 UTC,
    # because the service day counts from noon minus twelve hours. A copy fetched
    # at 07:30 UTC is in force, not the day's own.
    early = "gtfs/gtfs_bus-2026-11-01-aaaa.zip"
    during = "gtfs/gtfs_bus-2026-11-01-bbbb.zip"
    client = FakeClient([
        FakeBlob(early, datetime(2026, 11, 1, 7, 30, tzinfo=UTC)),
        FakeBlob(during, datetime(2026, 11, 1, 8, 30, tzinfo=UTC)),
    ])  # fmt: skip
    order = gtfs.candidates(client, "gtfs_bus", "20261101")
    assert [blob.name for blob in order] == [early, during]
    assert [blob.name for blob in gtfs.fetched_during(order, "20261101")] == [during]


def test_on_the_day_clocks_go_back_a_copy_fetched_after_midnight_is_the_days_own(
    tmp_path, monkeypatch
):
    # The service day runs 24 elapsed hours from day_base: 08:00 UTC on the 1st
    # to 08:00 UTC on the 2nd. A copy fetched at 12:00 UTC on the 1st (04:00 PST)
    # is the day's own. One fetched at 08:30 UTC on the 2nd is 00:30 on the next
    # service day, so it must not be used for the 1st even though it matches all
    # ten reported trips. The end bound is the next day's day_base, not a fixed
    # offset from this one's start.
    before = "gtfs/gtfs_bus-2026-10-31-aaaa.zip"
    during = "gtfs/gtfs_bus-2026-11-01-bbbb.zip"
    after = "gtfs/gtfs_bus-2026-11-02-cccc.zip"
    client = FakeClient([
        FakeBlob(before, datetime(2026, 10, 31, 12, tzinfo=UTC), holding(tmp_path / "a", ["OLD"])),
        FakeBlob(during, datetime(2026, 11, 1, 12, tzinfo=UTC), holding(tmp_path / "b", reported(8))),
        FakeBlob(after, datetime(2026, 11, 2, 8, 30, tzinfo=UTC), holding(tmp_path / "c", reported(10))),
    ])  # fmt: skip
    monkeypatch.setattr(gtfs, "FEEDS", {"gtfs_bus": "LACMTA"})

    chosen = gtfs.prepare(client, "20261101", tmp_path / "cache", {"LACMTA": set(reported(10))})
    assert chosen["LACMTA"].name == Path(during).stem


def test_a_day_with_no_raw_files_downloads_no_timetable(tmp_path, monkeypatch):
    def refused(*args, **kwargs):
        pytest.fail("looked for a timetable on a day with no raw files")

    monkeypatch.setattr(gtfs, "prepare", refused)
    monkeypatch.setattr(gtfs, "candidates", refused)
    with pytest.raises(SystemExit, match="no raw files found for 20260818"):
        cli.grade_day(
            lambda: pytest.fail("made a client"),
            "20260818",
            cache=tmp_path / "cache",
            out=tmp_path / "out",
            raw_dir=tmp_path / "empty",
            upload=False,
        )


def test_grading_a_day_picks_the_timetable_the_vehicles_trips_match(tmp_path, monkeypatch):
    # End to end through grade_day: the raw reports name T1 and T2, only the copy
    # fetched during the day has them, and the day's 8 scheduled stops come from it.
    raw = build_raw(tmp_path / "raw")
    client = FakeClient([
        FakeBlob(BEFORE, utc(8, 16, 12), holding(tmp_path / "old", ["OLD1", "OLD2"])),
        FakeBlob(DURING, utc(8, 18, 12), zipped(build_timetable(tmp_path / "new"))),
    ])  # fmt: skip
    monkeypatch.setattr(gtfs, "FEEDS", {"gtfs_bus": "LACMTA"})

    cli.grade_day(
        lambda: client,
        SERVICE_DATE,
        cache=tmp_path / "cache",
        out=tmp_path / "out",
        raw_dir=raw,
        upload=False,
    )
    saved = json.loads((tmp_path / "out" / cli.report_path(SERVICE_DATE)).read_text())
    assert saved["stats"]["scheduled_stops"] == 8


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

    target = cache / Path(AUG_16).stem
    real_extract = zipfile.ZipFile.extract
    at_death = {}

    def dies_mid_file(self, member, path=None, pwd=None):
        if member == "stop_times.txt":
            (Path(path) / member).write_bytes(b"trip_id,arriv")
            # A killed process runs no cleanup, so the disk at this moment
            # is what the next run finds. Record it before any handler runs.
            at_death["marker"] = (target / ".complete").exists()
            at_death["files"] = {p.name: p.read_bytes() for p in target.iterdir() if p.is_file()}
            raise OSError("killed while unpacking")
        return real_extract(self, member, path, pwd)

    monkeypatch.setattr(zipfile.ZipFile, "extract", dies_mid_file)
    with pytest.raises(OSError):
        gtfs.ensure_local(blob, cache)
    assert at_death["marker"] is False

    # Put the disk back the way the kill left it, undoing anything a cleanup
    # handler might have done, so the rerun starts where a real one would.
    target.mkdir(parents=True, exist_ok=True)
    for name, data in at_death["files"].items():
        (target / name).write_bytes(data)

    monkeypatch.undo()
    directory = gtfs.ensure_local(blob, cache)
    for path in source.iterdir():
        assert (directory / path.name).read_bytes() == path.read_bytes(), path.name
