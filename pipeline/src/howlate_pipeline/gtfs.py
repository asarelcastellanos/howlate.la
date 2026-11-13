"""Picks the timetable that was in force on a service day, and reads it.

Metro revises its schedules and the collector keeps every version, so the
question "what was this trip supposed to do" has a different answer depending on
when it is asked. Measuring August's buses against September's timetable gives
numbers that are wrong with nothing to show anything was amiss, which is the
whole reason the archive keeps every version rather than the latest one.

Two feeds, shaped differently, and the difference is load-bearing:

    bus    route_id "720-13201"   trip_id "10720013680644-JUNE26"
    rail   route_id "801"         trip_id "64863705"

so the line code is the part of route_id before the first hyphen in both cases,
which happens to be the whole string for rail.

Zips are cached on disk under their blob name. They are 22 MB and 1.4 MB and
never change once written, so a rerun of the same day re-downloads nothing.
"""

import csv
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from google.cloud import storage

from howlate_pipeline import BUS_AGENCY, RAIL_AGENCY, RAW_BUCKET, ZONE

PREFIX = "gtfs"

# feed name in the archive -> the agency its records carry
FEEDS = {"gtfs_bus": BUS_AGENCY, "gtfs_rail": RAIL_AGENCY}

# The files actually used. shapes.txt is 18 MB of route geometry that nothing
# here reads, so it is left in the zip.
NEEDED = [
    "calendar.txt",
    "calendar_dates.txt",
    "trips.txt",
    "stop_times.txt",
    "stops.txt",
    "routes.txt",
    "feed_info.txt",
]

# How much better, as a share of the trip_ids the vehicles reported, a copy
# fetched during the service day must match before it replaces the copy in force
# at the start of it. Even the best copy misses a few reported trips: on
# 2026-10-14 the copy fetched at 05:24 matched 1,322 of 1,348 reported rail
# trips and missed 26, all of them in its trips.txt under services that do not
# run that day. A perfect match is not expected, and on a day where the copy in
# force already matched, a different copy that matches a trip or two better
# would change a day that graded correctly for no reason.
MATCH_MARGIN = 0.005

DOW = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def day_base(service_date: str) -> float:
    """The instant that GTFS times on this service day are measured from.

    Not local midnight. The spec defines them against noon minus twelve hours,
    which is the same thing on all but two days a year and is correct on those
    two as well. Getting this wrong would shift an entire day's delays by an hour
    twice a year and look like a genuine service collapse.
    """
    noon = datetime.strptime(service_date, "%Y%m%d").replace(hour=12, tzinfo=ZoneInfo(ZONE))
    # Twelve elapsed hours, subtracted from the instant. Subtracting a
    # timedelta from an aware datetime moves the wall clock instead, which
    # lands on local midnight and is an hour wrong on exactly the two days
    # this exists for. That shipped once and was caught by a test.
    return noon.timestamp() - 12 * 3600


def day_bounds(service_date: str) -> tuple[float, float]:
    """The window a service day's records can fall in, generously bounded.

    Trips are stamped with their service date so this is only used to decide
    which UTC partitions to read, where reading a little too much is free and
    reading too little silently truncates the evening.
    """
    base = day_base(service_date)
    return base, base + 30 * 3600


def fetched_at(blob: storage.Blob) -> datetime:
    """When the collector fetched this copy."""
    fetched = (blob.metadata or {}).get("fetched_at")
    # Fall back to the upload time. The collector has always written
    # fetched_at, but a hand-copied file would not have it, and being unable
    # to read the archive is worse than being approximate about it.
    return datetime.fromisoformat(fetched.replace("Z", "+00:00")) if fetched else blob.updated


def candidates(client: storage.Client, feed: str, service_date: str) -> list[storage.Blob]:
    """Every copy of one timetable, best first.

    Best means newest that already existed when the service day began. This is
    the order of fallback, not the final choice: `prepare` can prefer a copy
    fetched during the day when the vehicles' trip_ids match it much better.
    A file fetched partway through the day, or the next morning, is not assumed
    to be a better description of today: Metro rolls the calendar forward when it
    republishes, and the copy taken on 19 August lists no service at all for the
    18th. Sorting those to the back rather than dropping them keeps them as a
    fallback for days where nothing earlier survives.
    """
    start, _ = day_bounds(service_date)

    scored = []
    for blob in client.list_blobs(RAW_BUCKET, prefix=f"{PREFIX}/{feed}-"):
        stamp = fetched_at(blob)
        # In force first, newest of those first; everything else after, oldest
        # of those first, so the nearest miss is tried before a distant one.
        in_force = stamp.timestamp() <= start
        scored.append(
            ((0 if in_force else 1, -stamp.timestamp() if in_force else stamp.timestamp()), blob)
        )

    if not scored:
        raise SystemExit(
            f"no {feed} timetable in the archive at all. "
            f"Collection starts 2026-08-18; earlier days cannot be measured."
        )

    return [blob for _, blob in sorted(scored, key=lambda pair: pair[0])]


def fetched_during(order: list[storage.Blob], service_date: str) -> list[storage.Blob]:
    """The copies fetched after the service day began and before the next one.

    Bounded by the next day's `day_base`, not by 24 hours added to this one's
    wall clock, which is an hour out on the day clocks go back.
    """
    start = day_base(service_date)
    following = datetime.strptime(service_date, "%Y%m%d") + timedelta(days=1)
    end = day_base(following.strftime("%Y%m%d"))
    return [blob for blob in order if start < fetched_at(blob).timestamp() < end]


def ensure_local(blob: storage.Blob, cache: Path) -> Path:
    """Download and unpack one timetable, once.

    Named after the blob, which carries the ETag, so two versions never collide
    and an existing directory is always the right contents rather than a
    same-named different file.
    """
    target = cache / Path(blob.name).stem
    marker = target / ".complete"
    if marker.exists():
        return target

    target.mkdir(parents=True, exist_ok=True)
    archive = target.with_suffix(".zip")
    blob.download_to_filename(archive)

    with zipfile.ZipFile(archive) as bundle:
        present = set(bundle.namelist())
        for name in NEEDED:
            if name in present:
                bundle.extract(name, target)

    archive.unlink()
    marker.touch()
    return target


def validity(directory: Path) -> tuple[str, str] | None:
    """The window this timetable claims to describe, if it says.

    The rail feed ships feed_info.txt with feed_start_date and feed_end_date both
    blank while the bus feed fills them in, so this returns None rather than
    pretending to a certainty the file does not offer.
    """
    info = directory / "feed_info.txt"
    if not info.exists():
        return None

    with info.open(encoding="utf-8-sig") as handle:
        row = next(csv.DictReader(handle), {})

    start, end = row.get("feed_start_date", ""), row.get("feed_end_date", "")
    return (start, end) if start and end else None


def check_covers(directory: Path, feed: str, service_date: str) -> None:
    """Warn if the timetable does not claim to describe this day.

    A warning and not a failure: the dates are advisory, sometimes blank, and
    calendar.txt is the real authority on which trips run. A run that stops here
    would refuse to measure a day it could measure perfectly well.
    """
    window = validity(directory)
    if window and not (window[0] <= service_date <= window[1]):
        print(
            f"  WARNING {feed}: feed covers {window[0]}..{window[1]}, "
            f"which does not include {service_date}"
        )


def active_services(directory: Path, service_date: str) -> set[str]:
    """The service_ids running on this date.

    calendar.txt gives the weekly pattern, calendar_dates.txt overrides it for
    named dates. The overrides are not an edge case: 18 August 2026 removed 40
    bus services, the school-day variants, because school was out.
    """
    weekday = DOW[datetime.strptime(service_date, "%Y%m%d").weekday()]

    active = set()
    with (directory / "calendar.txt").open(encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            if row["start_date"] <= service_date <= row["end_date"] and row[weekday] == "1":
                active.add(row["service_id"])

    exceptions = directory / "calendar_dates.txt"
    if exceptions.exists():
        with exceptions.open(encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                if row["date"] != service_date:
                    continue
                if row["exception_type"] == "1":
                    active.add(row["service_id"])
                elif row["exception_type"] == "2":
                    active.discard(row["service_id"])

    return active


def line_code(route_id: str) -> str:
    """The line as riders and the realtime feed spell it.

    "720-13201" is line 720; rail's "801" is already the answer. route_short_name
    looks like the right column and is not: it is blank for every rail line.
    """
    return route_id.split("-")[0].strip()


def trip_ids(directory: Path, services: set[str]) -> set[str]:
    """The trip_ids this copy runs on the day, given its active services."""
    with (directory / "trips.txt").open(encoding="utf-8-sig") as handle:
        return {row["trip_id"] for row in csv.DictReader(handle) if row["service_id"] in services}


def in_force_copy(
    feed: str, order: list[storage.Blob], service_date: str, cache: Path
) -> tuple[storage.Blob, Path, set[str]]:
    """The first copy, in `candidates` order, that lists any service running.

    A timetable with nothing scheduled is not a quiet edge case: it silently
    deletes a whole feed from the results, which is exactly what the 19 August
    rail copy did to the 18th before this loop existed. So an empty one is
    skipped, and running out of copies is fatal rather than an empty answer.
    """
    for blob in order:
        directory = ensure_local(blob, cache)
        services = active_services(directory, service_date)
        if services:
            return blob, directory, services
        print(f"  {feed}: {Path(blob.name).name} lists no service on {service_date}, trying older")

    raise SystemExit(
        f"no {feed} timetable in the archive lists any service on {service_date}. "
        f"Either the date is outside every schedule held, or the archive is incomplete."
    )


def prepare(
    client: storage.Client,
    service_date: str,
    cache: Path,
    observed: dict[str, set[str]] | None = None,
) -> dict[str, Path]:
    """Fetch and unpack the timetable that actually describes this service day.

    Starts from the copy in force when the day began (see `in_force_copy`). Given
    the trip_ids the vehicles reported, a copy fetched during the day replaces it
    when it matches clearly more of them. Time alone cannot decide this. The
    collector keeps a copy only when its content changes, so many days have no
    copy of their own. Of the 64 rail copies in the archive, 63 were fetched
    between 04:10 and 05:30 local, after the day began, and one, from
    2026-08-18, was fetched at 21:28 on the evening of 2026-08-17. Over the 82
    days from 2026-08-18 to 2026-11-07, the copy in force at midnight was dated
    one calendar day earlier on 60 days, two days earlier on 11, and three days
    earlier on 11.

    Read from each day's full raw files, 2026-10-14 reported 1,348 distinct rail
    trip_ids. The copy in force at midnight matched 26 of them (1.9%) and the
    copy fetched at 05:24 matched 1,322 (98.1%). On 2026-09-10 the figures were
    1,002 of 1,413 (70.9%) and 1,413 of 1,413. On 2026-11-05 and 2026-11-10 both
    copies matched 100%, so a rule that always preferred the later copy would
    change days that were right.

    A copy fetched during the day that cannot be read is skipped with a log
    line, so one bad file does not fail a day the copy in force can grade.

    `observed` maps an agency to its reported trip_ids. Without it, or for a feed
    with none, the copy in force is used as before.
    """
    ready = {}
    for feed, agency in FEEDS.items():
        order = candidates(client, feed, service_date)
        blob, directory, services = in_force_copy(feed, order, service_date, cache)

        seen = (observed or {}).get(agency, set())
        note = ""
        if seen:
            held = len(seen & trip_ids(directory, services))
            # The baseline is only "in force at midnight" when it was fetched
            # before the day began. When every earlier copy lists no service,
            # `in_force_copy` falls through to one fetched during the day.
            if fetched_at(blob).timestamp() <= day_base(service_date):
                baseline = "the copy in force at midnight"
            else:
                baseline = "the earliest copy with service"
            best = (held, fetched_at(blob), blob, directory, services)
            qualifying = []
            for other in fetched_during(order, service_date):
                if other.name == blob.name:
                    continue
                # A later copy is only a candidate to replace one that works, so
                # a file that will not open is skipped rather than failing a day
                # the copy in force can grade.
                try:
                    other_dir = ensure_local(other, cache)
                    other_services = active_services(other_dir, service_date)
                    got = len(seen & trip_ids(other_dir, other_services))
                except (FileNotFoundError, KeyError, zipfile.BadZipFile) as error:
                    print(
                        f"  {feed}: {Path(other.name).name} could not be read "
                        f"({type(error).__name__}), skipped"
                    )
                    continue
                if got - held > MATCH_MARGIN * len(seen):
                    qualifying.append((got, fetched_at(other), other, other_dir, other_services))
            # Highest match, ties to the newest.
            if qualifying:
                best = max(qualifying, key=lambda row: row[:2])
            matched, _, blob, directory, services = best
            note = (
                f", {matched / len(seen):.1%} of observed trips match "
                f"({baseline}: {held / len(seen):.1%})"
            )

        check_covers(directory, feed, service_date)
        print(
            f"  {feed}: {Path(blob.name).name}, "
            f"{len(services)} services active on {service_date}{note}"
        )
        ready[agency] = directory
    return ready
