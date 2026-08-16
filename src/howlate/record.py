"""Connects to Metro's live bus feed and writes every update to timestamped files.

Run it with:  .venv/bin/python -m howlate.record
Stop it with: Ctrl-C

Each line of a file is one complete message from Metro, exactly as sent, wrapped
with the time we received it. Nothing is summarized or dropped on the way in:
fields that look useless today are impossible to recover later.

A new file is started every five minutes. Finished files can be uploaded; the one
still being written cannot, which is the whole reason rotation exists.
"""

import asyncio
import os
import signal
from datetime import datetime, timezone
from pathlib import Path

import requests
import websockets

# 20 and 720 run Wilshire Bl, 204 and 754 run Vermont Av.
ROUTES = ["20", "204", "720", "754"]

# A websocket stays open so Metro can push updates whenever a bus reports in.
FEED = f"wss://api.metro.net/ws/LACMTA/vehicle_positions/{','.join(ROUTES)}"

DATA_DIR = Path("data")
ROTATE_SECONDS = 5 * 60

# A monitoring service URL, pinged once per finished file. Left unset the
# recorder works exactly the same, just unwatched. Kept in the environment
# rather than here because the URL is effectively a secret.
HEARTBEAT_URL = os.environ.get("HOWLATE_HEARTBEAT_URL", "")

# How long to wait for a message before waking up to look around anyway. Metro
# sends in bursts with 1 to 4 seconds of silence between them, and stops entirely
# overnight, so we cannot rely on a message arriving to trigger a rotation.
#
# One second, not ten: this interval is also how long it takes to notice a stop
# signal, and waiting ten seconds for Ctrl-C is miserable. An idle wakeup costs
# nothing.
CHECK_SECONDS = 1


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def stamp(moment: datetime) -> str:
    """2026-08-16T02:06:55.787401Z"""
    return moment.isoformat().replace("+00:00", "Z")


class RotatingFile:
    """One open file at a time, replaced every ROTATE_SECONDS."""

    def __init__(self, directory: Path, rotate_seconds: int):
        self.directory = directory
        self.rotate_seconds = rotate_seconds
        self.directory.mkdir(parents=True, exist_ok=True)
        self._file = None
        self._path = None
        self._opened_at = None
        self._lines = 0

    def _open(self) -> None:
        opened = utc_now()
        # Written as .partial, renamed to .jsonl on close. The uploader only
        # picks up .jsonl files, so it can never ship a half-written one.
        name = f"vehicle_positions-{opened.strftime('%Y%m%dT%H%M%SZ')}.jsonl.partial"
        self._path = self.directory / name
        self._file = self._path.open("w", encoding="utf-8")
        self._opened_at = opened
        self._lines = 0

    def write(self, message: str) -> None:
        if self._file is None:
            self._open()
        # message is Metro's raw text. Splicing it in rather than decoding and
        # re-encoding keeps the payload byte for byte.
        self._file.write(f'{{"received_at":"{stamp(utc_now())}","payload":{message}}}\n')
        self._file.flush()
        self._lines += 1

    def due(self) -> bool:
        if self._file is None:
            return False
        return (utc_now() - self._opened_at).total_seconds() >= self.rotate_seconds

    def close(self) -> Path | None:
        """Finish the current file. Returns it, or None if there was nothing."""
        if self._file is None:
            return None
        self._file.close()
        self._file = None

        if self._lines == 0:
            self._path.unlink(missing_ok=True)
            return None

        # Dropping the .partial suffix marks the file ready to upload. Renaming
        # is atomic, so the file is never seen in a half-renamed state.
        finished = self._path.with_suffix("")
        self._path.rename(finished)
        print(f"  finished {finished.name} ({self._lines} updates)")
        return finished


async def heartbeat() -> None:
    """Tell the monitor we are still alive, once per finished file.

    systemd restarts the recorder if it crashes, but nothing notices if the
    whole machine disappears or the feed goes silent while still connected.
    This does: a monitoring service emails if the pings stop arriving.

    A failure here must never interfere with collection, so everything is
    swallowed. Missing a heartbeat is worth an alert, not a lost recording.
    """
    if not HEARTBEAT_URL:
        return
    try:
        await asyncio.to_thread(requests.get, HEARTBEAT_URL, timeout=10)
    except Exception as error:
        print(f"  heartbeat failed ({type(error).__name__}), continuing anyway")


def recover_orphans(directory: Path) -> None:
    """Finish files left behind by a crash or a power cut.

    A clean stop renames the open file, but a hard kill leaves it as .partial,
    and the uploader only ships .jsonl. Without this, whatever was collected in
    the final minutes before a crash would sit on disk forever. Safe to run at
    startup: only one recorder runs at a time, so nothing else holds these open.
    """
    for path in sorted(directory.glob("*.jsonl.partial")):
        if path.stat().st_size == 0:
            path.unlink()
            continue
        finished = path.with_suffix("")
        path.rename(finished)
        print(f"  recovered {finished.name} from an unclean shutdown")


async def record() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    recover_orphans(DATA_DIR)

    spool = RotatingFile(DATA_DIR, ROTATE_SECONDS)

    # Ctrl-C sends SIGINT; a service manager stopping us sends SIGTERM. Python
    # turns neither into something asyncio.wait_for reliably breaks out of, so
    # both are handled explicitly: they set a flag the loop below checks.
    stopping = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stopping.set)

    print(f"recording routes {', '.join(ROUTES)} to {DATA_DIR}/")
    print(f"starting a new file every {ROTATE_SECONDS} seconds")
    print("press Ctrl-C to stop\n")

    backoff = 1.0
    try:
        # Connections drop: Metro restarts, wifi hiccups, a socket goes idle at
        # 4am. Any of those would otherwise end a month-long collection, so the
        # connection lives inside a loop that reconnects.
        while not stopping.is_set():
            try:
                # close_timeout defaults to 10 seconds: on exit the library
                # politely waits that long for Metro to acknowledge the
                # disconnect, and Metro does not answer. We are only reading.
                async with websockets.connect(FEED, close_timeout=1) as socket:
                    print("  connected")
                    backoff = 1.0

                    while not stopping.is_set():
                        # Wait for a message, but give up after CHECK_SECONDS so
                        # the rotation check below still runs when it is quiet.
                        try:
                            message = await asyncio.wait_for(
                                socket.recv(), timeout=CHECK_SECONDS
                            )
                        except asyncio.TimeoutError:
                            message = None

                        # No await between close and open, so this cannot be
                        # interrupted partway through. Messages arriving
                        # meanwhile wait in the socket buffer.
                        if spool.due() and spool.close():
                            await heartbeat()

                        if message is not None:
                            spool.write(message)

            except asyncio.CancelledError:
                raise
            except Exception as error:
                if stopping.is_set():
                    break
                print(f"  lost connection ({type(error).__name__}), retrying in {backoff:.0f}s")

                # Wait, but keep checking the rotation clock. The open file is
                # deliberately left open: a brief flap should not chop the
                # archive into fragments, while a long outage still rotates on
                # schedule so collected data does not sit here unuploaded.
                waited = 0.0
                while waited < backoff and not stopping.is_set():
                    if spool.due() and spool.close():
                        await heartbeat()
                    await asyncio.sleep(1)
                    waited += 1

                # Back off so a sustained outage does not hammer Metro, but cap
                # it so recovery is never more than a minute away.
                backoff = min(backoff * 2, 60)
    finally:
        # Reached on a stop signal and on any error, so the file in progress is
        # properly finished instead of being left looking still-in-progress.
        print("\nstopping")
        spool.close()


def main() -> None:
    asyncio.run(record())


if __name__ == "__main__":
    main()
