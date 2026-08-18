"""The file being written to disk, and its journey from open to shippable.

Nothing here knows about websockets. This module owns the spool directory and
the rules about what may be found in it; record.py owns the connections and
decides when to rotate.

A file passes through four names, and which name it wears is the only
conversation the recorder and the uploader ever have:

    vehicle_positions-<ts>.jsonl.partial     being written to right now
    vehicle_positions-<ts>.jsonl.raw         finished, waiting to be compressed
    vehicle_positions-<ts>.jsonl.gz.partial  being compressed right now
    vehicle_positions-<ts>.jsonl.gz          done, and the uploader's to take

There is no lock and no shared state, only renames, which are atomic within a
directory. A file is therefore never visible in a half-finished condition, and
either process can be killed at any instant without confusing the other.

Compression happens here rather than in the uploader because the network puts out
about 15 GB of raw text a day against 26 GB of free disk. Uncompressed, a Cloud
Storage outage fills the disk in under two days; compressed, in about three weeks.
"""

import gzip
import os
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

# Relative on purpose. systemd sets WorkingDirectory to /var/lib/howlate, so
# this resolves there on the VM and to ./data in the repository when run by hand.
DATA_DIR = Path("data")

PREFIX = "vehicle_positions"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def stamp(moment: datetime) -> str:
    """2026-08-16T02:06:55.787401Z"""
    return moment.isoformat().replace("+00:00", "Z")


def compress(raw: Path) -> Path:
    """Compress a finished file, replacing it with a .gz.

    The source is deleted last, after the result is atomically in place. Any
    crash then leaves either a source to redo or a finished result, never
    neither. The obvious order loses five minutes of already-safe data.

    Streamed rather than read whole: 50 MB files, 1 GB machine.
    """
    building = raw.with_suffix(".gz.partial")
    finished = raw.with_suffix(".gz")

    with raw.open("rb") as source, gzip.open(building, "wb", compresslevel=6) as target:
        shutil.copyfileobj(source, target, 1024 * 1024)

    os.replace(building, finished)
    raw.unlink()
    return finished


class RotatingFile:
    """The one file currently being written to, replaced on a fixed interval."""

    def __init__(self, directory: Path, rotate_seconds: int):
        self.directory = directory
        self.rotate_seconds = rotate_seconds
        self.directory.mkdir(parents=True, exist_ok=True)
        self._file = None
        self._path = None
        self._opened_at = None
        self._lines = 0
        self._by_agency = Counter()

    def _open(self) -> None:
        # Opened lazily, on the first message rather than on a clock, so the
        # quiet hours overnight leave no trail of empty files behind.
        opened = utc_now()
        name = f"{PREFIX}-{opened.strftime('%Y%m%dT%H%M%SZ')}.jsonl.partial"
        self._path = self.directory / name
        self._file = self._path.open("w", encoding="utf-8")
        self._opened_at = opened
        self._lines = 0
        self._by_agency = Counter()

    def write(self, agency: str, message: str) -> None:
        """Append one message from one feed.

        Spliced in as text, never decoded and re-encoded, so what lands on disk
        is byte for byte what Metro sent.

        No await in here, nor in close(). That is what makes them atomic against
        each other while both feeds write, and why there is no lock. Adding one
        would let the two feeds interleave inside a single line.
        """
        if self._file is None:
            self._open()

        self._file.write(
            f'{{"received_at":"{stamp(utc_now())}"'
            f',"agency":"{agency}"'
            f',"payload":{message}}}\n'
        )
        # Per line, so a hard kill loses nothing already accepted. Cheap enough
        # to be worth it: 400 messages a second is about 200 KB/s.
        self._file.flush()
        self._lines += 1
        self._by_agency[agency] += 1

    def due(self) -> bool:
        if self._file is None:
            return False
        return (utc_now() - self._opened_at).total_seconds() >= self.rotate_seconds

    def close(self) -> tuple[Path | None, Counter]:
        """Finish the open file and hand it on to be compressed.

        Returns None if nothing was written. The per-feed counts are how the
        caller notices one feed going silent while the other carries on.
        """
        if self._file is None:
            return None, Counter()

        self._file.close()
        self._file = None
        counted = self._by_agency

        if self._lines == 0:
            self._path.unlink(missing_ok=True)
            return None, counted

        finished = self._path.with_suffix(".raw")
        self._path.rename(finished)
        return finished, counted


def recover_orphans(directory: Path) -> None:
    """Pick up whatever a crash left behind, resuming each file where it stopped.

    Safe to run twice: only one recorder ever holds this directory.
    """
    for path in sorted(directory.glob(f"{PREFIX}-*.jsonl.partial")):
        if path.stat().st_size == 0:
            path.unlink()
            continue
        path.rename(path.with_suffix(".raw"))
        print(f"  recovered {path.name} from an unclean shutdown")

    # A compression that never finished. Its source is still on disk, because
    # compress() deletes that last, so the half-built result is simply discarded.
    for path in sorted(directory.glob(f"{PREFIX}-*.jsonl.gz.partial")):
        path.unlink()
        print(f"  discarded {path.name}, an unfinished compression")

    for path in sorted(directory.glob(f"{PREFIX}-*.jsonl.raw")):
        if path.with_suffix(".gz").exists():
            # Killed in the one instant between the result landing and the
            # source being removed. The work is done; finish the tidying.
            path.unlink()
            continue
        compress(path)
        print(f"  compressed {path.name}, left over from an unclean shutdown")
