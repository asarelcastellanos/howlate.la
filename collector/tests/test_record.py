"""Tests for the two rules that keep the recorder honest about being alive.

Run with:  .venv/bin/python collector/tests/test_record.py

These run against a real websocket server on localhost rather than a mock,
because the failure being tested is one that every mock would have passed. On 21
August 2026 Metro served a socket that was open, answered every keepalive ping,
and delivered nothing for sixteen hours. Nothing was broken in any way a fake
connection object could express: the bug was that the recorder believed a
connection instead of watching for data. So the server here is the real thing,
behaving exactly as Metro's did.

The clocks are shortened from minutes to seconds. The quantity being tested is
"does it give up on a quiet socket", not how long it waits first.
"""

import asyncio
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import websockets
from websockets.asyncio.server import serve

from howlate_collector import record, routes
from howlate_collector.spool import RotatingFile

MESSAGE = '{"vehicle":{"trip":{"tripId":"1"}}}'


class Server:
    """A stand-in for Metro, which can be told to stop talking.

    `connections` is the count that matters: reconnecting is the only externally
    visible thing the recorder does when it decides a socket is dead.
    """

    def __init__(self, *, burst: int, then_silent: bool):
        self.burst = burst
        self.then_silent = then_silent
        self.connections = 0
        self._server = None

    async def handle(self, socket):
        self.connections += 1
        try:
            for _ in range(self.burst):
                await socket.send(MESSAGE)
                await asyncio.sleep(0.05)

            if self.then_silent:
                # Open, healthy, and saying nothing. The library answers pings
                # underneath this, which is precisely why the recorder cannot
                # rely on the library to notice.
                #
                # Waiting on the close rather than on a future that never
                # resolves: this handler has to end when the recorder gives up,
                # or the server cannot be shut down at the end of the test.
                await socket.wait_closed()
            else:
                while True:
                    await socket.send(MESSAGE)
                    await asyncio.sleep(0.05)
        except websockets.ConnectionClosed:
            pass

    async def __aenter__(self):
        self._server = await serve(self.handle, "127.0.0.1", 0)
        self.port = self._server.sockets[0].getsockname()[1]
        return self

    async def __aexit__(self, *_):
        self._server.close()
        await self._server.wait_closed()


async def run_feed(server: Server, seconds: float, spool: RotatingFile) -> None:
    """Point the recorder at the local server and let it run for a while."""
    original = routes.feed_url
    routes.feed_url = lambda agency, codes: f"ws://127.0.0.1:{server.port}"
    stopping = asyncio.Event()
    task = asyncio.create_task(record.feed("LACMTA", [], spool, stopping))
    try:
        await asyncio.sleep(seconds)
    finally:
        stopping.set()
        await asyncio.wait_for(task, timeout=5)
        routes.feed_url = original


async def test_silent_socket_is_replaced(spool: RotatingFile) -> None:
    """The 21 August failure: connected, then nothing. It must not be tolerated."""
    async with Server(burst=3, then_silent=True) as server:
        await run_feed(server, seconds=5, spool=spool)

    # STALE_SECONDS is 1s here, so five seconds is room for several reconnects.
    # One connection means the recorder sat on a dead socket, which is the bug.
    assert server.connections >= 3, (
        f"expected repeated reconnects to a silent server, got {server.connections} connection(s)"
    )


async def test_delivering_socket_is_left_alone(spool: RotatingFile) -> None:
    """The false positive that would matter more than the bug.

    A watchdog that reconnects a working feed drops messages every time it
    fires. Metro's quietest measured five minutes still held 135 rail messages,
    so a feed that is delivering at all must be left completely alone.
    """
    async with Server(burst=0, then_silent=False) as server:
        await run_feed(server, seconds=5, spool=spool)

    assert server.connections == 1, (
        f"a feed delivering steadily was reconnected {server.connections} times"
    )


async def test_total_silence_raises_the_alarm() -> None:
    """Nothing arriving from either feed has to reach the outside world.

    The spool opens a file on the first message, so total silence produces no
    file, nothing falls due, and the rotator's ordinary path never runs. This is
    the case that ran for sixteen hours without a word.
    """
    pings = []
    original = record.heartbeat

    async def capture(suffix: str = "") -> None:
        pings.append(suffix)

    record.heartbeat = capture
    stopping = asyncio.Event()
    directory = Path(tempfile.mkdtemp())
    try:
        spool = RotatingFile(directory, rotate_seconds=1)
        task = asyncio.create_task(record.rotator(spool, stopping))
        await asyncio.sleep(5)
        stopping.set()
        await asyncio.wait_for(task, timeout=5)
    finally:
        record.heartbeat = original
        shutil.rmtree(directory, ignore_errors=True)

    assert pings.count("/fail") >= 2, (
        f"expected a repeating alarm during total silence, got {pings}"
    )


async def test_alarm_stays_quiet_while_data_flows() -> None:
    """The same alarm must never fire while files are being written."""
    pings = []
    original = record.heartbeat

    async def capture(suffix: str = "") -> None:
        pings.append(suffix)

    record.heartbeat = capture
    stopping = asyncio.Event()
    directory = Path(tempfile.mkdtemp())
    try:
        spool = RotatingFile(directory, rotate_seconds=1)

        async def write_steadily():
            while not stopping.is_set():
                spool.write("LACMTA", MESSAGE)
                spool.write("LACMTA_Rail", MESSAGE)
                await asyncio.sleep(0.05)

        writer = asyncio.create_task(write_steadily())
        task = asyncio.create_task(record.rotator(spool, stopping))
        await asyncio.sleep(5)
        stopping.set()
        await asyncio.wait_for(task, timeout=5)
        await asyncio.wait_for(writer, timeout=5)
    finally:
        record.heartbeat = original
        shutil.rmtree(directory, ignore_errors=True)

    assert "/fail" not in pings, f"alarmed while data was flowing: {pings}"
    assert pings.count("") >= 2, f"expected ordinary heartbeats, got {pings}"


def test_stalled_feeds_still_names_one_quiet_feed() -> None:
    """The older check, which catches one feed dying while the other carries on."""
    silent = Counter()
    agencies = ["LACMTA", "LACMTA_Rail"]
    counted = Counter({"LACMTA": 50_000})

    for _ in range(record.SILENT_FILES - 1):
        assert record.stalled_feeds(silent, counted, agencies) == []
    assert record.stalled_feeds(silent, counted, agencies) == ["LACMTA_Rail"]

    # And a single message clears it, so a reconnection is not an outage.
    assert record.stalled_feeds(silent, Counter({"LACMTA": 1, "LACMTA_Rail": 1}), agencies) == []


async def main() -> int:
    assert False, "deliberate failure to test branch protection"
    # Minutes in production, seconds here.
    record.CHECK_SECONDS = 0.1
    record.STALE_SECONDS = 1
    record.ALARM_SECONDS = 2

    directory = Path(tempfile.mkdtemp())
    spool = RotatingFile(directory, rotate_seconds=3600)

    tests = [
        ("a silent socket is replaced", test_silent_socket_is_replaced(spool)),
        ("a delivering socket is left alone", test_delivering_socket_is_left_alone(spool)),
        ("total silence raises the alarm", test_total_silence_raises_the_alarm()),
        ("no alarm while data flows", test_alarm_stays_quiet_while_data_flows()),
    ]

    failures = 0
    for name, coroutine in tests:
        try:
            # Bounded, because the thing being tested is a recorder that once
            # waited sixteen hours for a message. A test of that must fail
            # rather than join it.
            await asyncio.wait_for(coroutine, timeout=20)
            print(f"  ok    {name}")
        except AssertionError as error:
            failures += 1
            print(f"  FAIL  {name}\n          {error}")
        except TimeoutError:
            failures += 1
            print(f"  FAIL  {name}\n          hung, gave up after 20s")

    try:
        test_stalled_feeds_still_names_one_quiet_feed()
        print("  ok    one quiet feed is still named")
    except AssertionError as error:
        failures += 1
        print(f"  FAIL  one quiet feed is still named\n          {error}")

    shutil.rmtree(directory, ignore_errors=True)
    print(f"\n{len(tests) + 1 - failures}/{len(tests) + 1} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
