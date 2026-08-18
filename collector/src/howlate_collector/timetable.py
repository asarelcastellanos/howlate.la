"""Saves Metro's timetables whenever they change, and notices when lines change.

Run it with:  .venv/bin/python -m howlate_collector.timetable

Runs a few times a day under a systemd timer. Unlike the recorder this is not a
long-running process: it checks, acts if needed, and exits. Its exit status is
the signal, so systemd shows a failed unit rather than burying it in a log.

Metro publishes two timetables, buses at 22 MB and rail at 1.4 MB. Neither
changes often, so the check is cheap: ask only for the headers, compare the ETag
against the newest copy already saved, and download nothing when they match.

Every version is kept under its own name and never overwritten, because Metro
revises schedules and the same trip can be given a different scheduled time.
Measuring August's buses against September's timetable would produce numbers
that are wrong with nothing to show anything was amiss.

A changed timetable is also the only warning that Metro has added or dropped a
line, so each new one has its line list compared against routes.py.
"""

import re
import sys
from datetime import datetime, timezone

import requests
from google.cloud import storage

from howlate_collector import BUCKET, routes

PREFIX = "gtfs"

# Each timetable is saved under its own name and compared only against earlier
# copies of itself.
FEEDS = [
    ("gtfs_bus", routes.BUS_TIMETABLE, routes.BUS_ROUTES),
    ("gtfs_rail", routes.RAIL_TIMETABLE, routes.RAIL_ROUTES),
]

# Exit status when the timetables saved fine but the lines no longer match the
# ones the recorder subscribes to. Distinct from 1 so that a red unit does not
# imply the download failed.
DRIFTED = 2


def clean_etag(raw: str | None) -> str:
    """ETags arrive quoted, sometimes behind a W/ weak-comparison prefix."""
    return re.sub(r'^W/|"', "", (raw or "").strip())


def latest_saved_etag(bucket: storage.Bucket, feed: str) -> str | None:
    """The ETag of the newest copy of this one timetable, if any.

    Scoped to a single feed. Listing all of gtfs/ and taking the last name works
    only while one timetable is saved there: gtfs_rail sorts after gtfs_bus, so
    the bus check would start comparing itself against rail's fingerprint, never
    match, and re-download 22 MB every few hours forever.

    Newest by upload time rather than by name, because the name carries only the
    date and eight characters of the ETag, so two revisions in one day would
    otherwise be ordered by whichever fingerprint sorted higher.
    """
    blobs = list(bucket.list_blobs(prefix=f"{PREFIX}/{feed}-"))
    if not blobs:
        return None

    return (max(blobs, key=lambda blob: blob.updated).metadata or {}).get("source_etag")


def report_drift(feed: str, published: list[str], recorded: list[str]) -> bool:
    """Compare a timetable's lines against the ones we subscribe to."""
    added, gone = routes.drift(published, recorded)
    if not added and not gone:
        print(f"  {feed}: {len(published)} lines, unchanged")
        return False

    if added:
        print(f"  {feed}: NEW lines, not being recorded: {', '.join(added)}")
    if gone:
        print(f"  {feed}: lines no longer published: {', '.join(gone)}")
    print(f"  {feed}: refresh with 'python -m howlate_collector.routes', then redeploy")
    return True


def snapshot(bucket: storage.Bucket, feed: str, source: str, recorded: list[str]) -> bool:
    """Save this timetable if it changed. Returns True if its lines drifted."""
    head = requests.head(source, allow_redirects=True, timeout=60)
    head.raise_for_status()
    etag = clean_etag(head.headers.get("ETag"))

    previous = latest_saved_etag(bucket, feed)
    if etag and etag == previous:
        print(f"  {feed}: unchanged since last check ({etag[:8]}), nothing to do")
        return False

    print(f"  {feed}: changed (was {(previous or 'nothing')[:8]}, now {etag[:8] or '?'}), downloading")
    response = requests.get(source, timeout=600)
    response.raise_for_status()

    published = routes.codes_from_timetable(response.content)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    name = f"{PREFIX}/{feed}-{today}-{(etag or 'noetag')[:8]}.zip"

    blob = bucket.blob(name)
    # The full ETag is stored beside the file so the next run can compare against
    # it without depending on how the name is spelled. The line list is stored
    # too, so the archive records which lines each timetable described without
    # anyone having to open the zip.
    blob.metadata = {
        "source_etag": etag,
        "source_url": source,
        "fetched_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "route_codes": ",".join(published),
    }
    blob.upload_from_string(response.content, content_type="application/zip")

    print(f"  {feed}: saved gs://{BUCKET}/{name} ({len(response.content) / 1e6:.1f} MB)")

    # Only worth checking when a new timetable actually arrived: lines cannot
    # change without the timetable changing, so this costs nothing on the runs
    # that find nothing new.
    return report_drift(feed, published, recorded)


def main() -> None:
    bucket = storage.Client().bucket(BUCKET)

    failed, drifted = [], []
    for feed, source, recorded in FEEDS:
        # One timetable failing must not stop the other being checked.
        try:
            if snapshot(bucket, feed, source, recorded):
                drifted.append(feed)
        except Exception as error:
            print(f"  {feed}: failed: {type(error).__name__}: {error}")
            failed.append(feed)

    if failed:
        sys.exit(1)
    if drifted:
        sys.exit(DRIFTED)


if __name__ == "__main__":
    main()
