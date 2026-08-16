"""Compresses finished recording files and uploads them to Cloud Storage.

Run it with:  .venv/bin/python -m howlate.upload
Stop it with: Ctrl-C

Runs as its own process, separate from the recorder. It never touches the live
feed, so a slow or failed upload cannot interrupt collection: the recorder keeps
writing files and this drains the backlog whenever it can.

The two processes coordinate only through filenames. The recorder writes
`.jsonl.partial` while a file is open and renames it to `.jsonl` when finished.
This picks up `.jsonl` only, so it can never ship a half-written file.
"""

import gzip
import re
import signal
import time
from pathlib import Path

from google.cloud import storage

DATA_DIR = Path("data")
BUCKET = "howlate-raw"

# How often to look for new finished files.
SWEEP_SECONDS = 30

# vehicle_positions-20260816T022551Z.jsonl -> date and hour, which came from the
# recorder and are already UTC.
NAME_PATTERN = re.compile(r"vehicle_positions-(\d{8})T(\d{2})\d{4}Z\.jsonl$")


def destination(path: Path) -> str:
    """Where this file lives in the bucket.

    Laid out as dt=YYYY-MM-DD/hh=HH so that querying a single day later reads
    only that day's files instead of scanning the whole archive.
    """
    match = NAME_PATTERN.search(path.name)
    if not match:
        raise ValueError(f"unexpected filename: {path.name}")

    day, hour = match.group(1), match.group(2)
    dt = f"{day[:4]}-{day[4:6]}-{day[6:]}"
    return f"vehicle_positions/dt={dt}/hh={hour}/{path.name}.gz"


def upload_one(bucket: storage.Bucket, path: Path) -> bool:
    """Compress, upload, then delete. Returns False and keeps the file on failure."""
    target = destination(path)
    raw = path.read_bytes()

    try:
        bucket.blob(target).upload_from_string(
            gzip.compress(raw, compresslevel=6),
            content_type="application/gzip",
        )
    except Exception as error:
        print(f"  failed {path.name}: {error}")
        return False

    # Only deleted once the upload has actually succeeded.
    path.unlink()
    print(f"  uploaded {target}")
    return True


def sweep(bucket: storage.Bucket) -> None:
    # Sorted so the oldest backlog goes first. .partial files are skipped by
    # this pattern, which is the whole coordination mechanism.
    for path in sorted(DATA_DIR.glob("vehicle_positions-*.jsonl")):
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
        # Sleep in short slices so a stop signal is noticed promptly.
        for _ in range(SWEEP_SECONDS):
            if stopping:
                break
            time.sleep(1)

    print("\nstopped")


if __name__ == "__main__":
    main()
