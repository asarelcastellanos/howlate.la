"""Saves a copy of Metro's published timetable whenever it changes.

Run it with:  .venv/bin/python -m howlate.timetable

Meant to run once a day. Unlike the recorder this is not a long-running process:
it checks, acts if needed, and exits.

Metro publishes its schedule as a 22 MB zip. It does not change often, so the
check is cheap: ask only for the response headers, compare the ETag fingerprint
against the newest copy already saved, and download nothing if they match.

Every version is kept under its own name and never overwritten. Metro revises
schedules, and the same trip can be given a different scheduled time. Measuring
August's buses against September's timetable would produce numbers that are
quietly wrong, with nothing to show anything was amiss.
"""

import re
import sys
from datetime import datetime, timezone

import requests
from google.cloud import storage

SOURCE = "https://gitlab.com/LACMTA/gtfs_bus/-/raw/master/gtfs_bus.zip"

BUCKET = "howlate-raw"
PREFIX = "gtfs"


def clean_etag(raw: str | None) -> str:
    """ETags arrive quoted, sometimes with a W/ weak-comparison prefix."""
    return re.sub(r'^W/|"', "", (raw or "").strip())


def latest_saved_etag(bucket: storage.Bucket) -> str | None:
    """The ETag of the newest copy already in the bucket, if there is one."""
    blobs = sorted(bucket.list_blobs(prefix=f"{PREFIX}/"), key=lambda b: b.name)
    if not blobs:
        return None
    return (blobs[-1].metadata or {}).get("source_etag")


def snapshot() -> bool:
    """Save a copy if the timetable changed. Returns True if something was saved."""
    bucket = storage.Client().bucket(BUCKET)

    # A HEAD request asks only for the headers, so this costs a few hundred
    # bytes rather than 22 MB.
    head = requests.head(SOURCE, allow_redirects=True, timeout=60)
    head.raise_for_status()
    etag = clean_etag(head.headers.get("ETag"))

    previous = latest_saved_etag(bucket)
    if etag and etag == previous:
        print(f"  unchanged since last check ({etag[:8]}), nothing to do")
        return False

    print(f"  timetable changed (was {(previous or 'nothing')[:8]}, now {etag[:8] or '?'}), downloading")
    response = requests.get(SOURCE, timeout=600)
    response.raise_for_status()

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    name = f"{PREFIX}/gtfs_bus-{today}-{(etag or 'noetag')[:8]}.zip"

    blob = bucket.blob(name)
    # The full ETag is kept alongside the file so the next run can compare
    # against it without depending on how the filename is spelled.
    blob.metadata = {
        "source_etag": etag,
        "source_url": SOURCE,
        "fetched_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    blob.upload_from_string(response.content, content_type="application/zip")

    print(f"  saved gs://{BUCKET}/{name} ({len(response.content) / 1e6:.1f} MB)")
    return True


def main() -> None:
    try:
        snapshot()
    except Exception as error:
        print(f"  failed: {type(error).__name__}: {error}")
        sys.exit(1)


if __name__ == "__main__":
    main()
