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

`arrivals` measures one service day and writes one Parquet partition per
table, about 25 seconds for all 120 lines. `aggregate` reads every partition
of one layout version and emits the small JSON files a browser fetches. Both
upload to `gs://howlate-derived`. The live event-driven path is not built.

The layout is versioned, so days written by different code never mix:

```
arrivals/v2/service_date=YYYY-MM-DD/part-0.parquet   one row per scheduled stop
trips/v2/service_date=YYYY-MM-DD/part-0.parquet      one row per scheduled trip
arrivals/service_date=YYYY-MM-DD/                    v1, 18 and 19 August only
```

v2 adds `vehicle_id` and `departure_time` to arrivals, and the trips table.
`aggregate` reads `out/arrivals/v2` by default and never looks below the
`service_date=` level, so pointing it at the arrivals root reads v1 alone
instead of counting a day twice.

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

In the bucket each run goes under `site/runs/<UTC time>/`, and
`site/current.json` names the run to read. The pointer moves only after a run
is complete, so a reader never gets a mix of two runs.

Every cell carries what was measured *and* what was scheduled, because only
about half of all scheduled stops can be observed and a cell resting on three
sightings must not look like one resting on three hundred. Largest line file is
**19 KB gzipped**.

## The data contract

The site reads the files `aggregate` writes and nothing else. Each kind of file
has a JSON Schema (draft 2020-12) in `pipeline/schemas/`:

```
index.schema.json     site/index.json
status.schema.json    site/status.json
line.schema.json      site/lines/<line>.json
current.schema.json   site/current.json, the pointer to the latest run
```

The `description` on each field says what it means, in plain words, for the
people building the site. Every object sets `additionalProperties: false` and
lists every key as required. A number or string is `null` only where the code
can emit null, which today is a stop's `lat` and `lon`.

`pipeline/tests/test_contract.py` builds the site from the hand-made fixture day
and checks that every file validates. It renames each key in turn, and adds an
unknown key to each object, and checks that validation fails. It also fails when
`aggregate` writes a kind of file with no schema, or a schema has no file. A
change to an output field needs its schema in the same PR.

The schemas are not part of the runtime. The image copies `pipeline/src` only,
and `jsonschema` is in the `test` extra, not in `requirements.lock`. The test
skips only when it is not in a checkout, as in the container job, which mounts
`pipeline/tests` alone. `npm run types` in `web/` generates
`web/src/lib/data/types.ts` from these schemas, and CI fails when the committed
file is stale. See "Data" in `web/README.md`.

## Copying the site to R2

The public site reads its JSON from Cloudflare R2, which charges nothing for
egress. After `daily` publishes a run to `gs://howlate-derived`, it copies that
run to the R2 bucket `howlate`. It uploads every file under `site/runs/<run>/`,
then writes `site/current.json` last, and only if the derived bucket still names
that run. A copy that fails partway leaves R2 on the previous complete run. A
successful copy deletes R2 runs the pointer does not list, except the runs R2's
own pointer named before that copy, which the next copy deletes. A failed copy leaves
the graded days and the Cloud Storage site saved, but `daily` exits non-zero and
pings failure.

With none of these settings in the environment, the copy is skipped, as in local
runs and tests. With only some, it fails and names the missing ones.

```
R2_ENDPOINT            https://<account>.r2.cloudflarestorage.com
R2_ACCESS_KEY_ID       an R2 API token's key id, with write access to the bucket
R2_SECRET_ACCESS_KEY   its secret
R2_BUCKET              optional, defaults to howlate
```

`deploy/daily.sh` sets these on the Cloud Run job. To fill a bucket by hand, copy
a run, by default the one the derived pointer names.

```
python -m howlate_pipeline publish-r2 [--run 20261115T130000Z-a1b2c3]
```

The files are public and read-only, so `deploy/r2-cors.json` lets any origin GET
and HEAD them. Paste it in the dashboard under the bucket's Settings, CORS
Policy. Wrangler takes the same rules in its own shape:
`npx wrangler r2 bucket cors set howlate --file pipeline/deploy/r2-cors.wrangler.json`.
At 20 MB a day, about 0.6 GB a month leaves Google Cloud, cents at $0.12/GB.

## Measured

The whole network, both feeds, service day 2026-08-18. Not a sample and not an
estimate. These are the first numbers, from before arrivals were timed from the
last approach as well as from STOPPED_AT, which is why "measured" here counts
STOPPED_AT rows only. The comparison below has the current figures.

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

The daily report checks the join rate as `matched_rate`. Rail vehicles
sometimes report trips that Metro's timetable lists under a service starting on
a later date. Those trips have no scheduled stops, so they stay ungraded and
lower the raw `stats.join_rate`, which was 99.02% on 2026-11-14 with 5,370
observations on 338 trips. `matched_rate` counts them as matched and reports
their number as `stats.explained`. A trip that no timetable copy lists still
fails it. A second check, `explained_pct`, caps the explained share at 5% of
observations (0.98% on 2026-11-14), so a bug that marked most services inactive
cannot pass as explained.

The six bus lines that never appeared were exactly the six in `EVENT_ONLY` in
`collector/src/howlate_collector/routes.py`. Nothing else was missing.

Sizing, now from output rather than from the timetables:

| | |
|---|---|
| Rows per day | 881,057, one per scheduled stop |
| Rows per year | ~322 million |
| Parquet size, zstd | **4.4 bytes/row**, against 6.7 predicted |
| **Whole year of delay data** | **~1.4 GB** |

Those sizes predate the approach fallback too. With it, the v1 files for 18 and
19 August are 5.4 to 5.5 bytes/row, about 1.75 GB a year.

## v1 against v2

Checked on 2026-11-09 by grading 18, 19 and 20 August with the v0.1.0 code and
with the v2 code from the same raw files and timetables, on DuckDB 1.5.6. Rerun
after the vehicle and departure rules were tightened in review, with the same
results.

| | 18 Aug | 19 Aug | 20 Aug |
|---|---|---|---|
| Scheduled stops | 881,057 | 879,646 | 880,685 |
| Rows differing in any v1 column | **0** | **0** | **0** |
| Same, against the v1 files in the bucket | **0** | **0** | not graded in v1 |
| Timed arrivals (approach included) | 67.9% | 70.0% | 76.9% |
| Median delay, mid-route | +1.3 min | +1.4 min | +1.6 min |
| Timed arrivals naming a vehicle | 100% | 100% | 100% |
| Rows with a departure time | 433,290 | 462,792 | 547,613 |
| Departure before arrival | 0 | 0 | 0 |
| Median dwell, where the bus stopped | 11 s | 14 s | 19 s |
| Scheduled trips never seen | 235 (1.6%) | 268 (1.8%) | 259 (1.8%) |
| Trips carried by more than one vehicle | 348 | 331 | 313 |
| Arrivals Parquet, zstd | 7.5 bytes/row | 7.7 bytes/row | 8.2 bytes/row |
| Trips Parquet | 308 KB | 304 KB | 304 KB |

So v2 adds columns and changes nothing v1 measured. The two new columns raise a
year of arrivals from about 1.75 GB to about 2.5 GB, and the trips table adds
about 110 MB a year.

