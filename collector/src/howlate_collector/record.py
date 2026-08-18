"""Holds Metro's two live feeds open and writes everything they send to disk.

Run it with:  .venv/bin/python -m howlate_collector.record
Stop it with: Ctrl-C

routes.py says which lines to ask for, spool.py owns the file being written to.
This module owns the connections, the clock, and the heartbeat. It never talks
to Cloud Storage; upload.py picks up from the spool directory on its own.

Three tasks run side by side: one per feed, plus a rotator holding the clock.
Rotation is a separate task rather than something the feeds do between messages,
because a file must keep closing on schedule even while a connection is down. A
feed that cannot reconnect must not be able to strand the data the other feed is
still writing.

The thing worth knowing about this process is that it is the only part of
HowLate where a failure costs something permanent. Everything downstream reads
an archive that already exists and can be re-run. A minute not recorded here is
gone. Almost every decision in this file follows from that.
"""

import asyncio
import os
import signal
from collections import Counter

import requests
import websockets

from howlate_collector import routes
from howlate_collector.spool import DATA_DIR, RotatingFile, compress, recover_orphans

ROTATE_SECONDS = 5 * 60

# How long to wait for a message before waking up anyway. Metro sends in bursts
# with a few seconds of quiet between them, and stops entirely overnight, so a
# message arriving cannot be relied on to drive anything. This doubles as how
# long it takes to notice a stop signal, which is why it is one second and not
# ten: waiting ten seconds for Ctrl-C is miserable.
CHECK_SECONDS = 1

# How many files in a row one feed may contribute nothing to before it is
# treated as broken rather than merely quiet. Three files is fifteen minutes,
# far longer than any reconnection.
SILENT_FILES = 3

# A monitoring service, pinged once per finished file. Unset, the recorder
# behaves identically and simply goes unwatched. Kept in the environment because
# the URL is effectively a password.
HEARTBEAT_URL = os.environ.get("HOWLATE_HEARTBEAT_URL", "")


async def heartbeat(suffix: str = "") -> None:
    """Report in, so that silence from this machine is itself an alarm.

    Nothing inside a process can notice its own absence, or that it is still
    connected to a feed which quietly stopped sending. An outside watcher that
    expects a ping every five minutes can notice both.

    Failures are swallowed. A missed ping is worth an alert; it is not worth
    interrupting collection over.
    """
    if not HEARTBEAT_URL:
        return
    try:
        await asyncio.to_thread(requests.get, HEARTBEAT_URL + suffix, timeout=10)
    except Exception as error:
        print(f"  heartbeat failed ({type(error).__name__}), continuing anyway")


async def feed(
    agency: str, codes: list[str], spool: RotatingFile, stopping: asyncio.Event
) -> None:
    """Keep one feed connected and write whatever arrives.

    One of these per feed, each holding its own backoff, so a rail connection
    that is flapping never delays the buses reconnecting.
    """
    url = routes.feed_url(agency, codes)
    backoff = 1.0

    # Connections drop: Metro restarts, a socket goes idle at 4am. Any of those
    # would otherwise be the end of a month-long collection.
    while not stopping.is_set():
        try:
            # close_timeout defaults to ten seconds, spent politely waiting for
            # Metro to acknowledge a disconnect it never acknowledges. We are
            # only ever reading, so there is nothing to lose by not waiting.
            async with websockets.connect(url, close_timeout=1) as socket:
                print(f"  [{agency}] connected")
                backoff = 1.0

                while not stopping.is_set():
                    try:
                        message = await asyncio.wait_for(
                            socket.recv(), timeout=CHECK_SECONDS
                        )
                    except asyncio.TimeoutError:
                        continue

                    spool.write(agency, message)

        except asyncio.CancelledError:
            raise
        except Exception as error:
            if stopping.is_set():
                break
            print(f"  [{agency}] lost connection ({type(error).__name__}), retrying in {backoff:.0f}s")

            waited = 0.0
            while waited < backoff and not stopping.is_set():
                await asyncio.sleep(1)
                waited += 1

            # Back off so a long outage does not hammer Metro, but cap it so
            # recovery is never more than a minute away.
            backoff = min(backoff * 2, 60)


def stalled_feeds(silent: Counter, counted: Counter, agencies: list[str]) -> list[str]:
    """Tally one finished file against the silence counters, naming any feed now stalled.

    Only ever called for a file that had something in it, so at least one feed
    is known alive. A feed contributing nothing to such a file is therefore
    silent while another is delivering, which is a fault rather than a quiet
    hour. Overnight both feeds stop together, the file comes back empty and is
    discarded, and this is never reached.

    Mutates `silent`, which is the caller's memory across files.
    """
    for agency in agencies:
        silent[agency] = 0 if counted.get(agency) else silent[agency] + 1
    return [agency for agency in agencies if silent[agency] >= SILENT_FILES]


async def rotator(spool: RotatingFile, stopping: asyncio.Event) -> None:
    """Close, compress and hand over the open file every ROTATE_SECONDS."""
    agencies = list(routes.FEEDS)
    silent = Counter()

    while not stopping.is_set():
        await asyncio.sleep(CHECK_SECONDS)
        if not spool.due():
            continue

        finished, counted = spool.close()
        if finished is None:
            # Nothing arrived in five minutes, which is ordinary overnight.
            continue

        # In a thread because compressing fifty megabytes takes a couple of
        # seconds, and doing it here would stall both feeds for that long.
        shipped = await asyncio.to_thread(compress, finished)
        tally = ", ".join(f"{name}={count}" for name, count in sorted(counted.items()))
        print(f"  finished {shipped.name} ({tally})")

        stalled = stalled_feeds(silent, counted, agencies)
        if stalled:
            # Deliberately not gating the ordinary heartbeat on both feeds being
            # healthy: a thirty-second rail reconnect would then raise an alarm.
            print(f"  nothing from {', '.join(stalled)} in {SILENT_FILES} files, raising the alarm")
            await heartbeat("/fail")
        else:
            # After compressing, not before, so a heartbeat means the whole
            # chain worked rather than just the socket. A compressor that had
            # started failing would otherwise stay invisible until the disk
            # filled.
            await heartbeat()


async def record() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    recover_orphans(DATA_DIR)

    spool = RotatingFile(DATA_DIR, ROTATE_SECONDS)

    # Ctrl-C sends SIGINT, a service manager sends SIGTERM, and Python turns
    # neither into anything asyncio.wait_for reliably breaks out of. Both set a
    # flag the loops above check instead.
    stopping = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stopping.set)

    listed = ", ".join(f"{len(codes)} {agency}" for agency, (codes, _) in routes.FEEDS.items())
    print(f"recording {listed} to {DATA_DIR}/")
    print(f"starting a new file every {ROTATE_SECONDS} seconds")
    print("press Ctrl-C to stop\n")

    try:
        # Each feed swallows its own errors, so anything reaching here is a bug
        # rather than a bad night on the network. Letting it take the group down
        # and be restarted is the right answer to a bug; limping along
        # half-connected, quietly recording half the network, is not.
        async with asyncio.TaskGroup() as group:
            for agency, (codes, _) in routes.FEEDS.items():
                group.create_task(feed(agency, codes, spool, stopping))
            group.create_task(rotator(spool, stopping))
    finally:
        # Runs on a stop signal and on any error, so the file in progress is
        # finished rather than left looking like it is still being written.
        # Compressed inline: there may be no loop left to await a thread on.
        print("\nstopping")
        finished, _ = spool.close()
        if finished is not None:
            compress(finished)


def main() -> None:
    asyncio.run(record())


if __name__ == "__main__":
    main()
