"""Ships finished files out of the spool directory and into Cloud Storage.

Run it with:  .venv/bin/python -m howlate_collector.upload
Stop it with: Ctrl-C

record.py writes and compresses; this only ever moves what is already finished.
They never call each other and share nothing but the spool directory, so an
unreachable bucket cannot interrupt collection: files simply pile up on disk and
this drains them when it can.

Its own process rather than a thread inside the recorder, because a hung TLS
handshake or an expired credential should not be able to stall a socket read.
That separation is the reason collection never depends on upload succeeding.
"""

import re
import signal
import time
from pathlib import Path

from google.cloud import storage

from howlate_collector import BUCKET
from howlate_collector.spool import DATA_DIR, PREFIX

# How often to look for newly finished files.
SWEEP_SECONDS = 30

NAME_PATTERN = re.compile(rf"{PREFIX}-(\d{{8}})T(\d{{2}})\d{{4}}Z\.jsonl\.gz$")


def destination(path: Path) -> str:
    """Where this file belongs in the bucket.

    Partitioned dt=YYYY-MM-DD/hh=HH so that reading a single day later touches
    only that day's files instead of scanning the archive.

    The partition is a UTC day, taken from the recorder's own clock. Service
    days in Los Angeles are not UTC days, so anything reading these back has to
    span two partitions to cover one evening.
    """
    match = NAME_PATTERN.search(path.name)
    if not match:
        raise ValueError(f"unexpected filename: {path.name}")

    day, hour = match.group(1), match.group(2)
    dt = f"{day[:4]}-{day[4:6]}-{day[6:]}"
    return f"{PREFIX}/dt={dt}/hh={hour}/{path.name}"


def upload_one(bucket: storage.Bucket, path: Path) -> bool:
    """Upload one file and remove it. Returns False and keeps it on failure.

    Handed to the library as a filename so it streams, rather than read into
    memory first: these are fifty megabyte files on a one gigabyte machine.
    """
    target = destination(path)

    try:
        bucket.blob(target).upload_from_filename(path, content_type="application/gzip")
    except Exception as error:
        print(f"  failed {path.name}: {error}")
        return False

    # Deleted only once the upload has actually returned. A file kept after a
    # failed upload costs disk; a file deleted before a confirmed one is gone.
    path.unlink()
    print(f"  uploaded {target}")
    return True


def sweep(bucket: storage.Bucket) -> None:
    # Oldest first, so a backlog drains in the order it was collected. The glob
    # matches whole names, so a file still being written (.jsonl.partial),
    # waiting to be compressed (.raw), or mid-compression (.gz.partial) is
    # invisible here. That is the entire handshake with the recorder.
    for path in sorted(DATA_DIR.glob(f"{PREFIX}-*.jsonl.gz")):
        upload_one(bucket, path)


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    bucket = storage.Client().bucket(BUCKET)

    stopping = False

    def stop(*_):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    print(f"watching {DATA_DIR}/ for finished files, uploading to gs://{BUCKET}")
    print("press Ctrl-C to stop\n")

    while not stopping:
        sweep(bucket)
        # Slept in short slices so a stop signal is noticed promptly rather than
        # up to half a minute later.
        for _ in range(SWEEP_SECONDS):
            if stopping:
                break
            time.sleep(1)

    print("\nstopped")


if __name__ == "__main__":
    main()
