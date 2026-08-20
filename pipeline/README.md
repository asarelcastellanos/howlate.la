# Pipeline

Turns the raw archive into how late each bus and train actually was.

Built and running. This is what it does, the numbers it produces, and the traps
found the hard way against real collected data.

## Status

The collector went live on **18 August 2026** and is recording all 114 bus lines
and all 6 rail lines. The bucket was wiped clean before that, so the archive
starts there.

**Arrivals and aggregates are done.** Two commands:

```
python -m howlate_pipeline arrivals --service-date 2026-08-18
python -m howlate_pipeline aggregate
```

`arrivals` measures one service day and writes one Parquet partition, about 25
seconds for all 120 lines. `aggregate` reads every partition written so far and
emits the small JSON files a browser fetches. Both upload to
`gs://howlate-derived`. The live event-driven path is not built.

Rerunning either is safe: `arrivals` replaces one date and touches no other, and
`aggregate` is byte-identical over unchanged input.

Nothing is published yet. Roughly a month of collection is where patterns
separate from noise, so there is no hurry.

## What the collector already produces

```
gs://howlate-raw/
├── vehicle_positions/dt=YYYY-MM-DD/hh=HH/vehicle_positions-<ts>.jsonl.gz
├── gtfs/gtfs_bus-<date>-<etag>.zip
└── gtfs/gtfs_rail-<date>-<etag>.zip
```

One gzipped JSONL file every five minutes, 288 a day, around 1 GB a day
compressed from roughly 15 GB of raw text. Each line:

```json
{"received_at":"2026-08-18T04:42:54.123456Z",
 "agency":"LACMTA",
 "payload":{ ...Metro's message, byte for byte... }}
```

`agency` is `LACMTA` or `LACMTA_Rail` and decides which timetable the record is
measured against. Every timetable version is kept, so a trip is always compared
against the schedule that was in force at the time. Each zip carries the line
list it described in its object metadata.

## What it has to do

**Arrivals.** For each scheduled stop, when the vehicle actually got there and
how that compares to when it should have. One row per scheduled stop:

```
service_date  route_id  direction_id  trip_id  stop_id  stop_sequence
scheduled_time  actual_time  delay_seconds  source
```

**Aggregates.** Two grains, because the site asks two questions and the data
cannot support fine time and fine space at once. A stop-by-hour-of-week grid
averages 4.9 observations per cell after a month, so it is noise; pooling over
stops gives ~300 per cell, and pooling into six dayparts gives ~46.

```
site/status.json        days, coverage, totals
site/index.json         every line with headline numbers
site/lines/720.json     hour-of-week profile + per-stop dayparts
```

Every cell carries what was measured *and* what was scheduled, because only
about half of all scheduled stops can be observed and a cell resting on three
sightings must not look like one resting on three hundred. Largest line file is
**19 KB gzipped**.

## Measured

The whole network, both feeds, service day 2026-08-18. Not a sample and not an
estimate:

| | |
|---|---|
| Lines | 114, being 108 bus and 6 rail |
| Trips | 14,588 |
| Scheduled stops | 881,057 |
| Measured arrivals | 433,290 |
| Observations joining to a scheduled stop | **433,290 of 433,290** |
| Reported `stop_id` agreeing with the timetable | **100.00%** |
| Median delay, mid-route | +1.4 min |
| p75 / p95 / p99 | +4.3 / +11.7 / +20.6 min |
| Absurd values (>60 min) | 0.00% |

The six bus lines that never appeared were exactly the six in `EVENT_ONLY` in
`collector/src/howlate_collector/routes.py`. Nothing else was missing.

Sizing, now from output rather than from the timetables:

| | |
|---|---|
| Rows per day | 881,057, one per scheduled stop |
| Rows per year | ~322 million |
| Parquet size, zstd | **4.4 bytes/row**, against 6.7 predicted |
| **Whole year of delay data** | **~1.4 GB** |

