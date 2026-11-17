# Changelog

Every release of HowLate, newest first. Versions follow
[semantic versioning](https://semver.org). The plan for upcoming versions is in
[docs/release-plan.md](docs/release-plan.md).

## 0.4.0 - 2026-11-16

The first version of the site. `web/` builds a static site that reads the
pipeline's JSON from Cloudflare R2 and shows real numbers on the home page,
with a design system and three charts. The pipeline gets a fixed data contract,
a copy of each run to R2, and a fix for a rail check that failed on trips Metro
lists under a later start date.

### Added

- A static site in `web/`, built with SvelteKit, Tailwind v4 and shadcn-svelte.
  Every branch gets a Cloudflare Pages preview.
- A newspaper-style design system with Source Serif 4 and Inter, both hosted by
  the site, 171 kB of fonts in all. Rail line colors come from Metro's own
  `routes.txt`. Where a color fails 3:1 against the light page, the charts use a
  darker variant and the bullet keeps Metro's color. Light and dark follow the
  device. A `/design` page shows every piece.
- A contrast test of 50 color pairs against WCAG AA. CI runs it.
- Three charts, drawn with Observable Plot. The heatmap shows median delay by
  day and hour. The line chart shows the median and the 90th percentile across
  the week. The strip shows each stop's delay for the weekday rush. A heatmap
  hour with fewer than 5 arrivals is hatched and an hour with no service is
  dotted, so a two-arrival hour is never the worst hour.
- Error, empty and loading states for every chart, with a retry button on a
  failed load. A home page loads `status.json` from R2 and shows the days of
  data, the stops graded and the share measured.
- A typed data loader. A 404, a network failure or bad JSON comes back as an
  error value the page can show.
- Four strict JSON Schemas in `pipeline/schemas`, for `index.json`,
  `status.json`, each line file and `current.json`. A test builds the site from
  the fixture day and checks every file against them. Renaming a field, adding
  one or adding a file with no schema fails it. #113 renamed `coverage_pct` and
  CI failed in that test as intended. The PR was closed unmerged.
- TypeScript types generated from those schemas by `npm run types`. CI
  regenerates them and fails when the committed file is stale. A `web` CI job
  also runs the type check, the build and the tests.
- The daily job copies each run of the site to a Cloudflare R2 bucket named
  `howlate`, so the public site reads its JSON from R2, which charges no egress.
  It uploads every file of the run, then writes `site/current.json` last, and
  only when `gs://howlate-derived` still names that run, so a run that fails
  partway leaves R2 on the previous complete run. A failed copy exits non-zero
  and sends the failure ping, and the graded days stay saved. Without
  `R2_ENDPOINT`, `R2_ACCESS_KEY_ID` and `R2_SECRET_ACCESS_KEY`, it is skipped.
- `python -m howlate_pipeline publish-r2 [--run RUN]` copies a run on demand. It
  reads `gs://howlate-derived` and writes only R2.
- `pipeline/deploy/daily.sh` stores the two R2 secrets and the R2 endpoint on
  the job, and `pipeline/deploy/r2-cors.json` holds the bucket's CORS rules. The
  pipeline image gains boto3 and five packages it needs.

### Fixed

- The daily check failed on days when rail vehicles reported trips that
  `trips.txt` lists under a service whose `start_date` is after that day.
  `active_services` correctly skips those services, so the trips never reach the
  scheduled table and every observation on them counted as unmatched. Read from
  each day's full raw files and timetable copies:
  - 2026-11-14 had 5,370 observations on 338 trips, all route 801, and a raw
    join rate of 99.02%.
  - 2026-11-13 had 3,882 observations on 244 trips, all route 801, and 99.39%.
  - 2026-11-07 had 1,083 observations on 214 trips, all route 803, and 99.80%.
    This is the failure 0.3.0 listed as "cause not established".
  - On 2026-11-12 and 2026-10-31 every reported trip matched, and nothing
    changes.
- On 2026-11-14 the copy in force at midnight and the copy fetched that day both
  matched 998 of the 1,336 reported rail trips, so the copy in force stayed.
  Only the later copy lists 142 of the 338 future trips, so the explanation
  reads every copy that was compared, not only the chosen one.

### Changed

- The check named `join_rate` is now `matched_rate`. It counts an observation as
  matched when it joins to a scheduled stop or its trip is listed under a
  service that is not running that day, in any copy compared. Its range, 99.9 to
  100.0, is the same. An observation on a trip that no copy lists, or on a stop
  the timetable lacks for a trip that does run that day, still fails it.
- A new check, `explained_pct`, fails when more than 5% of a day's observations
  are explained, so a calendar bug that marked most services inactive cannot
  pass as explained. The measured shares are 0.98% on 2026-11-14, 0.61% on
  2026-11-13 and 0.20% on 2026-11-07, and 0 on 2026-11-12 and 2026-10-31.
- `stats.join_rate` in the report is unchanged. The report adds
  `stats.explained`, `stats.explained_trips`, `stats.matched_rate`,
  `explained_unmatched` (per feed) and `notes`.
- Explained trips are not graded. They have no scheduled stops, so they add no
  rows to `arrivals` or `trips`, and rail coverage on those days stays lower.

### Checked

- The pipeline's 192 tests, ruff lint and ruff format pass. The web type check,
  lint, build and 25 tests pass, and `npm run types` leaves no diff.
- Every CI job passed on #107, #108, #110, #111, #112, #114 and #115, and the
  Cloudflare Pages preview deployed on #110 to #115.
- The charts and home page were checked at 375 and 1280 px in light and dark,
  against the real data on R2 and an unreachable data address. Nothing scrolled
  sideways and the console had no errors.
- The public R2 development address serves `site/current.json` for run
  `20261116T130339Z-ef4438`, which names 117 files, the same run Cloud Storage
  names.
- Regrading 2026-11-14, 2026-11-13, 2026-11-07, 2026-11-12 and 2026-10-31
  locally, with no upload, exits 0 and passes every check on all five.

### Not done yet

- The live daily job does not copy to R2 until this release is merged and
  `pipeline/deploy/daily.sh` is run. The R2 secrets are in Secret Manager, and
  the run on R2 now was copied by hand with `publish-r2`.
- Reports already in `gs://howlate-derived` keep the old `join_rate` check name
  until those days are graded again.

### Known gaps

- No screenshot gate compares pixels. The baselines differ between macOS and the
  Linux runner, so the screenshots are saved for review.
- The data address is Cloudflare's `r2.dev` development address, which is
  rate-limited. A custom domain for the data is not set up.
- Naming the failed day in the failure ping (#100) and skipping site files left
  over on a reused disk (#86) moved to 0.5.0.
- A "Workers Builds: howlate-la" check fails on every pull request. It comes
  from a Cloudflare Workers project that was deleted and is not part of the
  build, so it does not block merges, and it needs Cloudflare support to remove.
  The Pages previews and every CI job pass.

### Not changed

- The collector. Its code did not change, so it stays at 0.1.0 and the VM is
  not redeployed.

## 0.3.0 - 2026-11-12

Every collected day is graded, and every new day is graded without anyone
running anything. The raw bucket now moves old files to cheaper storage.

### Added

- A container for the pipeline, installed from a hashed dependency lock so a
  rebuild cannot pick up a different version.
- A resumable `backfill` command that grades a date range and skips days that
  already have a report.
- A `daily` command that grades the last seven days that have no report,
  rebuilds the site files from every finished day, and pings healthchecks.io.
  A day that fails sends the failure ping, and the site is still rebuilt from
  the days that finished.
- A Cloud Run job, `howlate-daily`, started by Cloud Scheduler at 05:00
  Pacific. It runs with `--max-retries 0`, so a retry cannot clear a failure
  ping.
- A GitHub Actions workflow that builds the image and points the job at it when
  a pipeline change reaches `main`. It waits for the checks on that exact
  commit and uses Workload Identity Federation, so no key file exists.
- Each day's `report.py` numbers saved as JSON in `reports/v2/`.
- The site files publish all at once, under a new run prefix, and
  `site/current.json` switches to it last. A run that crashes before that
  leaves the previous site files in place.
- A lifecycle rule for `gs://howlate-raw`: `vehicle_positions/` moves to
  Coldline after 30 days and Archive after 365. `gtfs/` stays Standard. It was
  applied on 2026-11-10, after the backfill, so grading does not pay retrieval
  fees on those days.

### Fixed

- Each day is now graded against the timetable copy that matches the trips the
  vehicles reported. The collector keeps a copy only when its content changes,
  so many days have no copy of their own. Of the 64 rail copies in the archive,
  63 were fetched between 04:10 and 05:30 local, after the day began, and one,
  from 2026-08-18, was fetched at 21:28 on the evening of 2026-08-17. Over the
  82 days from 2026-08-18 to 2026-11-07, the copy in force at midnight was dated
  one calendar day earlier on 60 days, two days earlier on 11, and three days
  earlier on 11. On 2026-09-10 that copy matched 1,002 of the 1,413 distinct
  rail trip_ids the vehicles reported (70.9%), and the copy fetched at 05:28
  that morning matches all 1,413. On 2026-10-14 it matched 26 of 1,348 (1.9%),
  and the copy fetched at 05:24 matches 1,322 (98.1%). The 26 it misses are in
  its trips.txt, under services that do not run that day. The figures were read
  from each day's full raw files. A copy fetched during the day replaces the one
  in force at midnight only when it matches more than 0.5 percentage points more
  of the reported trips, so a day that already graded correctly keeps its copy.
  A same-day copy that cannot be read is skipped and logged. The log shows the
  match rate of both.
- Lines 9 and 22 no longer fail the silent-lines check. The timetable schedules
  them on 24 days and the vehicle feed never reported a stop on either. Of those
  24 days, 23 now pass. 2026-08-21 still fails, because lines 128 and 202 were
  also silent that day. Lines 694 to 697 stay under the check. Line 697 was
  scheduled on 6 days and reported on every one of them, so a silent 697 would
  be a fault. The report lists the exempt lines separately as
  `silent_event_lines`, and a silent line that is not exempt still fails the
  check.
  Reports of days with no silent shuttle line have no `silent_event_lines`
  field, and a missing field means none.

### Checked

- The 05:00 Pacific runs on 2026-11-10, 2026-11-11 and 2026-11-12 each started
  from the scheduler, exited with code 0 and published 117 site files, with no
  manual step.
- The backfill ran on a Spot VM in us-west1 on 2026-11-09 and graded 82 days,
  2026-08-18 to 2026-11-07, at about 1 minute 45 seconds each. After the
  timetable and shuttle fixes, 25 days were graded again on 2026-11-12, Pacific
  time: 2026-09-10, 2026-10-14 and 2026-11-07, then the 22 days on which only
  lines 9 and 22 were silent. All 85 reports, 2026-08-18 to 2026-11-10, now
  exist. 81 pass every check. The 4 that fail are 2026-08-21 (the 16-hour dead
  socket the collector now detects), 2026-09-04 and 2026-09-22 (one STOPPED_AT
  record on a trip's final stop each), and 2026-11-07 (join rate 99.80%, cause
  not established, carried to 0.4.0). The notes are on #16.
- The cold storage rule moved raw files older than 30 days to Coldline on
  2026-11-11, and files from 2026-10-14 on stayed Standard. At list prices the
  raw bucket costs about $1.00 a month, against about $2.15 if everything had
  stayed Standard.

### Removed

- The v1 files for 18 and 19 August in `gs://howlate-derived/arrivals/`.
  They were two files, 9.2 MiB. Every day, including those two, has a v2
  report.

### Not changed

- The collector. Its code did not change, so it stays at 0.1.0 and the VM is
  not redeployed.

## 0.2.0 - 2026-11-09

Arrivals v2: every graded stop now says which vehicle it was and when it left,
every scheduled trip gets a row, and the pipeline has tests. This is the
foundation the backfill in 0.3.0 grades every collected day with, once.

### Added

- `vehicle_id` and `departure_time` on every arrival. The vehicle is the one
  whose report set the arrival, and the departure is that same bus's last
  STOPPED_AT, so a trip that changes vehicles or is claimed by two buses is
  attributed stop by stop. A report with no vehicle id is left unknown rather
  than credited to another bus.
- A trips table: one row per scheduled trip with reports, first and last seen,
  vehicles, and stops scheduled against stops observed. On 18 to 20 August,
  235 to 268 trips a day were never seen at all.
- A versioned layout, `arrivals/v2/` and `trips/v2/`. The v1 files for 18 and
  19 August stay where they are, and `aggregate` reads one version.
- Pipeline tests on a hand-built service day, 49 in all, run in CI on Python
  3.11 and 3.14.
- Two `report.py` checks: timed arrivals name a vehicle, and most scheduled
  trips were seen.
- Release steps for deploying, watching and rolling back the collector, and a
  review rule against docs claiming more than the data shows.

### Fixed

- On the two days a year the clocks change, every scheduled time was an hour
  off, so every delay those days was wrong by 3,600 seconds. 1 November 2026 is
  in the archive and would have been graded wrong. No published numbers were
  affected.
- `duckdb>=1.1` installed DuckDB 2.0, which removed a method the pipeline calls
  five times, so every fresh install crashed. DuckDB is pinned to 1.5.6; moving
  to 2.0 is #73.

### Checked

- 18, 19 and 20 August graded with v0.1.0 and with v0.2.0: zero rows differ in
  any v1 column across 2,641,388 rows.

### Not changed

- The collector. Nothing in `collector/` changed, so it stays at 0.1.0 and the
  VM is not redeployed.

## 0.1.0 - 2026-11-09

The first tagged version. It names what was already running before versions
existed, and adds the checks every later change goes through.

### Already running

- The collector has recorded both of Metro's live feeds since 18 August 2026,
  apart from 16 hours on 21 August when Metro kept a socket open and sent
  nothing. It covers all 114 scheduled bus lines and all 6 rail lines, about 25
  million records a day, shipped to `gs://howlate-raw` every five minutes.
- It saves a copy of Metro's timetables whenever they change, and leaves its
  systemd unit failed when Metro adds a line that is not being recorded or
  drops one that is.
- It replaces a socket that is open but silent, and raises an alarm through
  healthchecks.io when either feed stops delivering.
- The pipeline grades one service day into one row per scheduled stop
  (`arrivals`) and summarises every graded day into the JSON files the site will
  read (`aggregate`). It has been run on 18 and 19 August.

### Added

- `CLAUDE.md`, `REVIEW.md` and the release plan.
- ruff linting and formatting for both packages.
- A GitHub Actions workflow for every PR: ruff, then each package installed on
  its own and every module imported, then the collector tests, on Python 3.11
  and 3.14.
- Branch protection on `main` and every `release/*` branch: changes arrive
  through a PR with passing checks, and the branches cannot be force-pushed or
  deleted.
- Issue forms and a PR template.
- This changelog.

### Changed

- The README matches the code: pipeline status, monthly cost, and typos.
