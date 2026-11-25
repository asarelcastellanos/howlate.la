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

`aggregate --no-upload` writes the site to a local folder and uploads nothing,
but it still reads Cloud Storage unless the inputs are local. `--from-bucket`
reads the arrivals from `gs://howlate-derived`, and without `--gtfs-dir` it
reads the timetables from `gs://howlate-raw`. Both are read-only, and the
timetables are what name the lines and give each line its mode.

Outside Google Cloud, `arrivals`, `backfill` and `daily` refuse to download raw
files that are not already in the cache. Reading `gs://howlate-raw` from the
internet costs about $0.12 per GiB, and 259 GiB read from a laptop on
2026-11-16 to 2026-11-18 cost $19.11 in egress and $3.49 in Coldline retrieval.
The refusal comes before the first download and states the number of files,
their size in GiB, the estimated cost, and that the read is free on the backfill
VM. Runs that find every file in the cache, and `--raw-dir` runs, are not
refused. The guard passes at once when `CLOUD_RUN_JOB` is set, as it is on every Cloud
Run job. Otherwise it asks the metadata server for the project id, so Compute
Engine VMs pass.

To grade from the archive, run `bash pipeline/deploy/backfill-vm.sh`. It
creates a temporary Spot VM in `us-west1-b`, runs `backfill` over a range of
days from a git ref, copies its log to `gs://howlate-derived/logs/`, and powers
off. A powered-off VM still bills for its disk, so delete it after each run:

```bash
gcloud compute instances delete howlate-backfill --zone us-west1-b
```

To run an analysis script over the raw archive instead, pass `--script` with a
repo-relative path under `pipeline/` that ends in `.py` and exists at the git
ref:

```bash
bash pipeline/deploy/backfill-vm.sh --script pipeline/scripts/count_positions.py \
  <git-ref> 2026-11-20 2026-11-20
```

With one date, the range runs through the latest complete service day, which
can be several days of 1.2 GB each. Pass the first and the last day for a
one-day run.

The VM runs the script once per service day in the range, in the same checkout
and Python environment as `backfill`, as
`python <script> --service-date YYYYMMDD --cache <dir> --out <dir>`. The script
reads raw files through `arrivals.fetch_raw` and writes its results under
`--out`. After each day the VM copies them to
`gs://howlate-derived/logs/scripts/<script-name>/<run-id>/<day>/` and
clears that day's raw cache. The wrapper copies only under
`gs://howlate-derived/logs/scripts/`. The analysis script itself is trusted
code that runs with the pipeline service account, which can write anywhere in
`gs://howlate-derived` and can only read `gs://howlate-raw`.

A Spot reclaim deletes the VM and loses the day in progress. Running the
command again without `--run` starts the whole range over under a new run id.
Add `--run <id>` to reuse that id as the output prefix, and the new VM skips
each day that already has its `_done` object. The run prints its id and the
exact resume command when it starts. The id may hold only letters, digits,
`_` and `-`, and `--run` needs `--script`.

A day that fails shows only as "not saved" in the run log, so check the log
and the `_done` objects. The log goes to `gs://howlate-derived/logs/` as in
`backfill` mode. Script mode writes nothing to `gs://howlate-raw` or to
`arrivals/`, `trips/`, `reports/` and `site/`, so it skips the check that the
daily schedule is paused. The same reminder applies, delete the VM after each
run.

### Finding why rail trip ids disagree

`pipeline/scripts/rail_runs.py` rebuilds each rail vehicle's runs from latitude
and longitude alone, ignoring the reported `trip_id`, and fits each run to the
running trips of its route and direction by the times at the stations it
passed. A route that the timetable runs as separate pieces, as 801 did on
2026-11-13 (a 13 stop piece and a 30 stop piece), gets one station list for each
piece. The unit is one run, and the id counted for it is the most common id the
vehicle reported during the run. The script classes that id as the fitted trip,
the vehicle's previous trip (stale), another trip on the same route and
direction (with the offset in trips within one piece, and in minutes), another
route or direction, a trip whose service is not running that day, or no id. It
also counts the records with a position, the ids per run, where in the run the id
changes, and how the run fits the later-start trips that run on that weekday. A
rail vehicle id names a set of cars and one train can appear under more than one
id, so it also counts runs with a twin, another vehicle id fitted to the same
trip at the same time. It is an investigation tool and writes nothing the site
reads.

Archive runs happen only on the backfill VM, which reads the raw archive for
free. Never run the script against the buckets from a laptop.

```bash
bash pipeline/deploy/backfill-vm.sh --script pipeline/scripts/rail_runs.py \
  <git-ref> 2026-11-13 2026-11-15
```

Each day writes `rail_runs_<day>.json` (a summary per route), `rail_runs_<day>.csv`
(one row per run) and `rail_timetable_<day>.json` (the trips each timetable copy
lists by service and stop pattern, and the stops the vehicles reached beyond the
station lists) under
`gs://howlate-derived/logs/scripts/rail_runs/<run-id>/<day>/`. The timetable copy
is chosen as the pipeline chooses it, with the trip ids the vehicles reported
that day, and only that copy's running services are candidates. A fit is
confident when the best trip is within 120 seconds and the next trip is at
least 120 seconds worse. That keeps only runs within 120 seconds of a trip, so
the confident set selects on-time trains. The summary reports every class for all
runs and for the confident runs, because a vehicle late by half a headway fits
two trips equally.

To repeat the local check on a hand-built day, with no bucket access, make two
folders from the pattern in `pipeline/tests/fixture_day.py`. In RAW, write
`vehicle_positions/dt=YYYY-MM-DD/hh=HH/*.jsonl.gz` as `build_raw` does, but with
`agency` set to `LACMTA_Rail` and `payload.vehicle.position.latitude` and
`longitude`, `trip.startTime` and `trip.routeId` on each record. In GTFS_RAIL,
write `calendar.txt`, `trips.txt` (with `direction_id`), `stop_times.txt` and
`stops.txt` (with coordinates about 1.8 km apart) as `build_timetable` does.
Then run

```bash
python pipeline/scripts/rail_runs.py --service-date YYYYMMDD --out OUT \
  --raw-dir RAW --gtfs-dir GTFS_RAIL
```

and read `OUT/rail_runs_<day>.csv`. A vehicle that reports trip A while running
trip B shows `class` `same_line` or `stale`, and one that reports a trip under
a service that starts later shows `not_in_force`.

### Grading rail by position

The rail matcher is built and ships switched off (`railmatch.ENABLED` is
`False`), because it missed the 95 percent agreement rule on 2026-11-18 and
2026-11-19 (#178). While it is off, every rail run is graded on its reported
trip, as before, and `rail_misfit_pct` is advisory. It still runs, prints and
saves, but a failure does not fail the day.

Rail trip ids are wrong on days when a line runs as split pieces (#177). With the
matcher on, `arrivals.match_rail_runs` grades each rail run on the trip it ran
when the id does not check out. `railmatch.py` rebuilds the runs from latitude
and longitude and decides each one. The reasons and the thresholds are in
`docs/adr/0002-match-rail-runs-by-position-when-the-id-fails.md`.

- Trusted. The most common reported id is a trip of the copy in force with a
  running service, and the most common startTime is within 120 seconds of its
  first departure, and the run is not a misfit under the `rail_misfit_pct`
  rule. The run is graded as before. A misfit goes on to the next rule.
- Matched. Otherwise the run is fitted to the trips in force on its station
  list and direction. A fit is confident when the best trip is within 120
  seconds and the next trip is at least 120 seconds worse. The run is graded
  against that trip, and its rows have `source` `matched`.
- Ungraded. Any other run, and any rail report outside every run, is dropped
  before grading.

With the matcher on, the report lists the three counts per line as
`rail_matching`, and `rail_misfit_pct` fails the day again. The agreement numbers
behind the decision to leave it off are on #178. Set `ENABLED` to `True` to grade
by position.

Two scripts measure it on the backfill VM, as `rail_runs.py` does.
`rail_hide_and_compare.py` hides the id of each trusted run, fits it by position
and counts how often the confident fit is the reported trip. `rail_regrade.py`
grades one day with the matcher off and on, writes both days under `--out` with no
upload, and counts what became of the trip ids that sit only under later-start
services.

```bash
bash pipeline/deploy/backfill-vm.sh --script pipeline/scripts/rail_regrade.py \
  <git-ref> 2026-11-13 2026-11-15
```

`pipeline/scripts/hash_day.py` grades one day with the checkout's code and
writes the row count and an order-independent hash of every column of `arrivals`
and `trips`. Run it from two refs and compare the files.

The
`--allow-egress` flag on `arrivals` and `backfill` forces the download and
accepts the cost. Only the owner uses it. The guard covers vehicle positions
under `vehicle_positions/`. Timetables under `gtfs/` are not guarded because the
whole prefix is 0.2 GB, and `gs://howlate-derived` is not guarded.

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
site/network.json       hour-of-week profile for the network, bus and rail
site/health.json        the daily report's results for the newest 14 days
```

In the bucket each run goes under `site/runs/<UTC time>/`, and
`site/current.json` names the run to read. The pointer moves only after a run
is complete, so a reader never gets a mix of two runs.

Every cell carries what was measured *and* what was scheduled, because only
about half of all scheduled stops can be observed and a cell resting on three
sightings must not look like one resting on three hundred.

Bus stops that the vehicle feed never reported get a time from the reports on
either side (`arrivals.interpolate`, source `interpolated`). Those delays are in
`n`, the median and `ontime` like any other. Each entry in `index.json`, each
direction's `all`, each stop and each scope's `all` in `network.json` carries
`est`, how many of its `n` arrivals were estimated, and `status.json` carries
`estimated_arrivals`. Hour and daypart cells do not, to keep the line files
small. The estimate is bus only. `pipeline/scripts/hide_and_compare.py` checks
it against stops that have a real report and prints the error by gap size.

Each profile hour, each stop's `all`, each direction's `all`, each entry in
`index.json` and each network profile hour also carries `ontime`, the percent of
measured arrivals from 60 seconds early to 300 seconds late, both included.
That is Metro's window, from its 2025 Transit Service Policies and Standards,
and bus and rail use the same one. It is not Metro's published on-time
performance. Metro scores bus at timepoints and rail at terminals, and HowLate
scores the arrival at every scheduled stop, so the two figures differ. A
daypart cell has no `ontime`, because the cells are most of a line file's size
and the pages read `med` from them.

`health.json` is for the behind-the-scenes page. It holds `pipeline_version`,
`last_day` and `days` from the run, `recent`, and `checks`. `recent` has one
entry for each of the newest 14 service days that have a saved report, newest
first, with `ok`, the names of the checks that `failed`, `coverage_pct`,
`estimated_pct` (the share of scheduled stops that were estimated, not in
`coverage_pct`), `explained_trips`, `explained_pct` and `observations`. `checks` is the checks of the
report for `last_day`, with the report's own labels, either a range (`value`,
`low`, `high`) or a count (`value`, `expected`). It is empty when `last_day` has
no readable report, even if `recent` lists older days. The file is public, so
`pipeline/src/howlate_pipeline/health.py` copies only those fields and no other
part of a report. A report saved before 0.4.0 names the join check `join_rate`
and has no explained fields, which read as 0. A day with no report is missing
from `recent`, and a report that cannot be read is skipped with a line in the
log. Without reports, as in `aggregate --no-upload` over a folder with none,
`recent` and `checks` are empty and the file is still written.

`aggregate` reads the reports from `reports/v2` beside the arrivals folder, which
is where `arrivals` writes them (`out/reports/v2` for `out/arrivals/v2`).
`--from-bucket` and `daily` instead download the newest 14 days' `report.json`
files, about 3 KB each, into `reports/v2` under the cache, from the same listing
as the arrivals so the file never names a day the rest of the site lacks.
`--reports DIR` reads them from another folder, and cannot be combined with
`--from-bucket`. Built from the real reports through 2026-11-15, the file is 3,876 bytes (980 gzipped).

Three more levels carry the same numbers over every measured arrival on every
day and hour.

- Each stop has `all` with `med`, `p90`, `pct5` and `ontime`. Its `cells` split
  the same arrivals by daypart and leave out a daypart with none, so `all` is
  the one number per stop. The count is the stop's own `n`. A stop with nothing
  measured has an `n` of 0 and nulls in `all`.
- Each direction in a line file has `all` with `n`, `med`, `p90`, `pct5` and
  `ontime`, and each entry in `index.json` has the same five numbers for the
  whole line.
- `network.json` has `network`, `bus` and `rail`, each with `all` and an
  hour-of-week `profile` of up to 168 entries. A mode with nothing measured is
  still there, with an `n` of 0 and an empty profile. A line counts in the mode
  its `index.json` entry shows.

Measured on the data through 2026-11-15, which is 90 service days, the largest
line file is line 92. Gzipped, it was 55,793 bytes (324,249 raw) before the
on-time work and is 59,733 bytes (342,297 raw) now. This section used to say
19 KB. The cells are most of the weight. Line 92 has 4,167 of them, and the file
gzips to about 16 KB without them. Adding `ontime` to every cell and an `n` to
every stop's `all` took it to 70,022 bytes, so both were dropped.

## The data contract

The site reads the files `aggregate` writes and nothing else. Each kind of file
has a JSON Schema (draft 2020-12) in `pipeline/schemas/`:

```
index.schema.json     site/index.json
status.schema.json    site/status.json
line.schema.json      site/lines/<line>.json
network.schema.json   site/network.json
health.schema.json    site/health.json
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

With none of the first three settings in the environment, the copy is skipped,
as in local runs and tests, unless `R2_REQUIRED` is set. With only some, it
fails and names the missing ones. The failure ping and the log show that text,
which names variables and never a value.

```
R2_ENDPOINT            https://<account>.r2.cloudflarestorage.com
R2_ACCESS_KEY_ID       an R2 API token's key id, with write access to the bucket
R2_SECRET_ACCESS_KEY   its secret
R2_BUCKET              optional, defaults to howlate
R2_REQUIRED            anything but 0, false, no, off, none or empty: missing R2 settings fail the run
R2_PUBLIC_URL          https://data.howlate.la, where the public reads the data, no path
```

`R2_REQUIRED` stops a redeploy that loses the settings from skipping the copy
and pinging success while the public site goes stale. The failure ping says so.
Any other value counts as set, so a typo such as `on` cannot turn the guard off.

After a copy that moves R2's pointer, `daily` checks the public address from
outside. It fetches `site/current.json` with a changing query, to get past its 60
second cache, then the `status.json` the pointer names. It fails the run when a
fetch fails or is not 200, a body is not JSON, the pointer names an older run
than the one copied, or `last_day` is more than 3 days before today's date in
Los Angeles. The job grades yesterday at 08:00 Pacific, so right after a run
the gap is 1, and a gap of 2 is normal for a run started by hand before 07:00. The check compares with the calendar, not with the site the job just
built, because the public file is that same build. A newer run passes. Each
fetch has a 10 second timeout and one retry.

With `R2_PUBLIC_URL` unset the check is skipped. When `R2_REQUIRED` is set, a
missing or invalid `R2_PUBLIC_URL` instead fails the daily run before anything is
copied. `publish-r2` neither reads `R2_PUBLIC_URL` nor probes, and it prints a
settings or guard failure as one line and exits 1.

A failure ping names every failed day within 1000 characters. A day whose
grading raised has its error's first non-empty line, as in
`20261107 failed: SystemExit: no raw files`. A day that only failed its checks
reads `20261107 failed its checks`, and one that only failed its cleanup reads
`20261107 cleanup failed`. Each line is cut to 160 characters. When the days do
not all fit, the ping ends with `and N more days`. URLs, `gs://` and `s3://`
paths and email addresses in an error are replaced with placeholders, in any
letter case. A URL is replaced up to the next space, so a quote or bracket inside
it does not end the match and leave the rest of a signed URL in the ping. A bare
hostname is not replaced.

Known behaviour. When a newer run appears during the copy, R2's pointer is left
alone and the job still pings success. R2 keeps serving the previous complete
run, the check is skipped because that is no fault of this copy, and the next
daily copy moves the pointer.

`deploy/daily.sh` sets these on the Cloud Run job. It accepts only
`https://` and a dotted domain name for `R2_ENDPOINT` and `R2_PUBLIC_URL`, such
as `https://data.howlate.la`. The name has at least two labels, each made of
letters, digits and inner hyphens, with single dots between them and none at the
end. The last label may not be all digits, which rules out an IPv4 address, and
`localhost` has no dot. There is no port, path, trailing slash, query, fragment
or user, so a value that `daily` would reject never deploys. To fill a bucket by hand, copy
a run, by default the one the derived pointer names.

```
python -m howlate_pipeline publish-r2 [--run 20261115T130000Z-a1b2c3]
```

The files are public and read-only, so `deploy/r2-cors.json` lets any origin GET
and HEAD them. The origin stays `*` because the data is public, and because
preview deployments on pages.dev subdomains need to read it. The site reads the
bucket through the custom domain `https://data.howlate.la`. Paste it in the dashboard under the bucket's Settings, CORS
Policy. Wrangler takes the same rules in its own shape:
`npx wrangler r2 bucket cors set howlate --file pipeline/deploy/r2-cors.wrangler.json`.
At 20 MB a day, about 0.6 GB a month leaves Google Cloud, cents at $0.12/GB.

## Commute files

The daily site build also writes `commute/`, which the commute page reads. It holds one
file per bus line, direction and day type, `commute/stops.json` and `commute/index.json`.
Each file gives every trip's time at every stop on the days of the last 56 service days,
rounded to 10 seconds and coded as the change from the stop before. The format is in the
docstring of `howlate_pipeline/commute.py`, and the reasons and the 450,000 byte limit are in
[ADR-0004](../docs/adr/0004-split-commute-files-by-direction-and-day-type.md). A file over the
limit gzipped makes `build_site` return 1, so the daily job reports the day as failed, and the site
is still published. `scripts/commute_build.py` runs the whole build on the backfill VM over 56
days and reports file count, sizes, time and peak memory.

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
their number as `stats.explained`.

A trip is explained only when no timetable copy lists it under a running
service and every copy that lists it does so under a service whose
`calendar.txt` `start_date` is after the day. A trip under an expired service,
a service that runs on another weekday, or one that a `calendar_dates.txt` row
removes stays unexplained and fails `matched_rate`, as does a trip no copy lists
and a service with no `calendar.txt` row. Only the later start date has been
measured as a cause.

Two more checks limit the explained set. `explained_pct` caps it at 5% of
observations (0.98% on 2026-11-14), so a bug that marked most services later
cannot pass as explained. It cannot see a small part of the network, because
rail is about 4% of observations. `explained_lines` fails when any line has at
least 5 observed trips and every one of them is explained, so a whole line
cannot be hidden. A line that is only partly explained passes, as route 801 did
on 2026-11-14 with 338 explained trips and 233 matched ones.

`rail_misfit_pct` catches a rail trip id that names the wrong run. A run is one
vehicle on one trip of the grader's observations, which is the trip it graded
(see "Grading rail by position"). For each run, the check takes the median gap
between when the vehicle first stopped at each stop and when a trip scheduled
it, and does this for the reported trip and for every other trip on the same
route and direction. A run is a misfit when another trip is within 60 seconds
and the reported trip is 300 seconds or more worse. Only runs timed at 5 or
more non-origin stops count, and a trip with no scheduled stops cannot be
judged, so later-start trips stay with `explained_pct`. The check is the
highest misfit share on any rail line with at least 30 judged runs, and fails
above 10%. It is per line because all rail dilutes it: on 2026-11-13 route 801
had 71 misfits in 331 runs (21.5%) and all rail had 5.3%. The report lists
every line's runs and misfits as `rail_misfits`.

While the rail matcher is off, `rail_misfit_pct` is advisory. It still runs, prints
`CHECK` with a note when it fails, and is saved as failed in the report and in
`health.json`. But it does not make the day's `ok` false, so `grade_day` returns 0,
`daily` exits 0 and the heartbeat is not sent as failed. Every other check fails the
day as before. Setting `railmatch.ENABLED` to true makes the check binding again.

This is a half-archive validation. It was measured on 48 of the 91 days from
2026-08-18 to 2026-11-16: 08-18 to 09-18 except 09-19, 09-20 to 09-27, 10-24,
10-25, 10-31, 11-07, 11-10, 11-13, 11-14 and 11-15. The highest line was a
median 2.6%. Six days were over 10%: 2026-08-22 (14.5%, route 805), 09-15
(10.8%, 805), 09-18 (11.2%, 805), 11-13 (21.5%, 801), 11-14 (24.4%, 801) and
11-15 (18.3%, 801). The other 42 were at most 9.0%. Raising the fit window from
60 to 120 seconds put the median at 7.9% and 14 days over the limit, because a
train a few minutes late is close to the trip behind it. A train that really ran
a headway late also fits the trip behind it, so some of the baseline is real
lateness and not a bad id. The other 43 days were not measured, 2026-09-19
among them because it failed to load. The days were read from the raw files
only to 07:59 UTC the next day, which leaves out the end of the service day after
local midnight on the days after 1 November. The full pipeline on 2026-11-13
found 70 misfits in 342 runs on route 801 (20.5%), against 71 in 331 (21.5%) in
the measurement, so a share near the limit can differ by about a point.

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

