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

Everything here judges a feed by what it delivers, never by whether it is
connected. A socket that is open and quiet is treated as broken and replaced,
and silence from both feeds at once raises the alarm on its own rather than
waiting for a file that will never be written. Both rules exist because the
opposite was assumed once and cost a day of collection.

The thing worth knowing about this process is that it is the only part of
HowLate where a failure costs something permanent. Everything downstream reads
an archive that already exists and can be re-run. A minute not recorded here is
gone. Almost every decision in this file follows from that.
"""

import asyncio
import os
import signal
import time
from collections import Counter

import requests
import websockets

from howlate_collector import routes
from howlate_collector.spool import DATA_DIR, RotatingFile, compress, recover_orphans

ROTATE_SECONDS = 5 * 60

# How long to wait for a message before waking up anyway. Metro sends in bursts
# with a few seconds of quiet between them, so a message arriving cannot be
# relied on to drive anything. This doubles as how long it takes to notice a
# stop signal, which is why it is one second and not ten: waiting ten seconds
# for Ctrl-C is miserable.
CHECK_SECONDS = 1

# How long a connected feed may deliver nothing before its socket is treated as
# dead and replaced. Both feeds send around the clock: across the first 1,422
# files there was not one in which either feed contributed zero records, and the
# quietest five minutes ever recorded still held 13,396 bus and 135 rail
# messages, at 3am and 2am respectively. So five minutes of silence is already
# far outside anything Metro has ever done, while being several times longer
# than the slowest reconnection.
STALE_SECONDS = 5 * 60

# How long nothing at all may reach the spool before the alarm goes up. Longer
# than STALE_SECONDS on purpose, so a feed that goes quiet gets one reconnection
# to fix itself before anybody is woken.
ALARM_SECONDS = 10 * 60

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


async def feed(agency: str, codes: list[str], spool: RotatingFile, stopping: asyncio.Event) -> None:
    """Keep one feed connected and delivering, and write whatever arrives.

    One of these per feed, each holding its own backoff, so a rail connection
    that is flapping never delays the buses reconnecting.

    Connected is not the same as working, and the difference cost a day. On 21
    August 2026 Metro's server errored, came back a minute later, accepted both
    subscriptions and then sent nothing for sixteen hours without ever closing
    the socket. Every layer below this one was satisfied: the TCP connection was
    open, and the server answered each keepalive ping, so the library had no
    reason to raise anything. Only this function knows that a feed which is not
    delivering is not working, whichever side has stopped.
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
                last_message = time.monotonic()

                while not stopping.is_set():
                    try:
                        message = await asyncio.wait_for(socket.recv(), timeout=CHECK_SECONDS)
                    except TimeoutError:
                        quiet = time.monotonic() - last_message
                        if quiet < STALE_SECONDS:
                            continue
                        # Leaving the block closes the socket, and the loop above
                        # opens a new one immediately. No backoff: this is not a
                        # server refusing connections, it is one handing out a
                        # connection that does not work, and the next one may.
                        print(
                            f"  [{agency}] connected but silent for "
                            f"{quiet / 60:.0f} min, reconnecting"
                        )
                        break

                    last_message = time.monotonic()
                    spool.write(agency, message)

        except asyncio.CancelledError:
            raise
        except Exception as error:
            if stopping.is_set():
                break
            print(
                f"  [{agency}] lost connection ({type(error).__name__}), retrying in {backoff:.0f}s"
            )

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
    hour. Both feeds silent together is a different fault, and the rotator
    catches that one, because no file is produced at all for it to appear in.

    Mutates `silent`, which is the caller's memory across files.
    """
    for agency in agencies:
        silent[agency] = 0 if counted.get(agency) else silent[agency] + 1
    return [agency for agency in agencies if silent[agency] >= SILENT_FILES]


async def rotator(spool: RotatingFile, stopping: asyncio.Event) -> None:
    """Close, compress and hand over the open file every ROTATE_SECONDS.

    Also the only thing that notices total silence. The spool opens a file on
    the first message rather than on a clock, so when nothing is arriving there
    is no file, nothing ever falls due, and every line below is skipped. That is
    what made sixteen missing hours look exactly like a working recorder with
    nothing to say.
    """
    agencies = list(routes.FEEDS)
    silent = Counter()
    last_delivery = time.monotonic()

    while not stopping.is_set():
        await asyncio.sleep(CHECK_SECONDS)
        if not spool.due():
            if time.monotonic() - last_delivery >= ALARM_SECONDS:
                print(f"  nothing from either feed in {ALARM_SECONDS // 60} min, raising the alarm")
                await heartbeat("/fail")
                # Reset, so a long outage reports every ALARM_SECONDS rather
                # than once. A watcher hearing nothing further cannot tell a
                # continuing outage from a recovery it missed.
                last_delivery = time.monotonic()
            continue

        finished, counted = spool.close()
        last_delivery = time.monotonic()
        if finished is None:
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
