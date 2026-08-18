"""The lines HowLate subscribes to, and how to read them out of a timetable.

record.py turns these lists into websocket addresses; timetable.py checks them
against what Metro publishes. Both import from here so there is one answer to
"which lines are we recording" rather than two that can drift apart.

Buses and rail are separate feeds with their own agency codes and their own
timetables, which is why the lists are separate too.

Keeping the list here, rather than reading it from a timetable at startup, is a
deliberate trade. It goes stale between deploys, but the recorder never fails to
start because a download did. Staleness is visible and recoverable; a recorder
that will not start is neither.

Metro reshuffles service every June and December, and the list changes more
often than that: 697 appeared in July 2025, 857 was deleted a month before,
three Intuit Dome shuttles arrived in January 2026. Refresh it with:

    .venv/bin/python -m howlate_collector.routes
"""

import csv
import io
import zipfile

BUS_AGENCY = "LACMTA"
RAIL_AGENCY = "LACMTA_Rail"

BUS_TIMETABLE = "https://gitlab.com/LACMTA/gtfs_bus/-/raw/master/gtfs_bus.zip"
RAIL_TIMETABLE = "https://gitlab.com/LACMTA/gtfs_rail/-/raw/master/gtfs_rail.zip"

# Generated from the timetables published 2026-08-16, by main() below.
BUS_ROUTES = [
    "2", "4", "9", "10", "14", "16", "18", "20", "22", "28", "30", "33",
    "35", "40", "45", "51", "53", "55", "60", "62", "66", "70", "74", "76",
    "78", "81", "90", "92", "93", "94", "102", "105", "108", "110", "111",
    "115", "117", "120", "125", "127", "128", "134", "150", "152", "154",
    "155", "158", "161", "162", "164", "165", "166", "167", "169", "179",
    "180", "182", "202", "204", "205", "206", "207", "209", "210", "211",
    "212", "217", "218", "222", "224", "230", "232", "233", "234", "236",
    "237", "240", "242", "244", "246", "251", "258", "260", "265", "266",
    "267", "268", "287", "294", "296", "344", "460", "487", "501", "550",
    "577", "601", "602", "605", "611", "617", "660", "662", "665", "690",
    "694", "695", "696", "697", "720", "754", "761", "901", "910",
]

RAIL_ROUTES = ["801", "802", "803", "804", "805", "807"]

# Stadium shuttles: they only run on game days. Plenty of ordinary lines are
# peak-only too, so silence never means broken on its own, only silence while
# the timetable says the line should be running.
EVENT_ONLY = {"9", "22", "694", "695", "696", "697"}

FEEDS = {
    BUS_AGENCY: (BUS_ROUTES, BUS_TIMETABLE),
    RAIL_AGENCY: (RAIL_ROUTES, RAIL_TIMETABLE),
}


def feed_url(agency: str, codes: list[str]) -> str:
    """The websocket address for one feed.

    A code that does not exist still connects, and then simply never sends
    anything. A typo here looks exactly like a quiet Sunday.
    """
    return f"wss://api.metro.net/ws/{agency}/vehicle_positions/{','.join(codes)}"


def codes_from_timetable(archive: bytes) -> list[str]:
    """The line codes in a timetable zip, spelled the way the feed expects.

    Not route_short_name, the obvious-looking choice: it holds a blank, pairs
    written "10/48", and strings like "Dodger Stadium Express". A slash in the
    address comes back as a 403 that reads like a permissions problem.
    """
    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        with bundle.open("routes.txt") as handle:
            rows = csv.DictReader(io.TextIOWrapper(handle, "utf-8-sig"))
            codes = {row["route_id"].split("-")[0].strip() for row in rows}

    return sorted(codes - {""}, key=_numeric)


def drift(published: list[str], recorded: list[str]) -> tuple[list[str], list[str]]:
    """Lines the timetable has that we do not, and lines we have that it does not."""
    added = sorted(set(published) - set(recorded), key=_numeric)
    gone = sorted(set(recorded) - set(published), key=_numeric)
    return added, gone


def _numeric(code: str) -> tuple[int, str]:
    """Sort 2 before 10 before 102, rather than lexically."""
    return (len(code), code)


def main() -> None:
    """Print the lists above, refreshed from the timetables Metro publishes now."""
    import textwrap

    import requests

    for agency, (recorded, url) in FEEDS.items():
        response = requests.get(url, timeout=600)
        response.raise_for_status()
        published = codes_from_timetable(response.content)

        added, gone = drift(published, recorded)
        state = "unchanged" if not (added or gone) else f"+{len(added)} -{len(gone)}"
        print(f"# {agency}: {len(published)} lines ({state})")

        name = "BUS_ROUTES" if agency == BUS_AGENCY else "RAIL_ROUTES"
        body = ", ".join(f'"{code}"' for code in published)
        print(f"{name} = [")
        for line in textwrap.wrap(body, width=72):
            print(f"    {line}")
        print("]\n")


if __name__ == "__main__":
    main()
