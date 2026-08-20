"""Turns the raw archive into how late each vehicle actually was.

One row per scheduled stop: where a vehicle was supposed to be, when it actually
got there, and the difference. Runs once a day over the previous service day.

    gtfs.py      picks the timetable that was in force, and reads it
    arrivals.py  matches observations to scheduled stops, computes the delay
    report.py    the sanity checks, printed on every run
    __main__.py  the command line

Nothing here writes to the raw bucket. The archive is append-only and this reads
it; a bug in the analysis must never be able to damage the collection.
"""

__version__ = "0.1.0"

# The bucket the collector writes to. Read-only from here.
RAW_BUCKET = "howlate-raw"

# Where this package's own output goes. Kept apart from the raw archive so that
# nothing here can ever write into the one set of files that cannot be rebuilt.
# Everything in this bucket is derived and can be thrown away and recomputed.
DERIVED_BUCKET = "howlate-derived"

# Every scheduled time in GTFS is an offset from local midnight on the service
# day, so every conversion in this package goes through this zone and never
# through the machine's own.
ZONE = "America/Los_Angeles"

BUS_AGENCY = "LACMTA"
RAIL_AGENCY = "LACMTA_Rail"
