# Changelog

Every release of HowLate, newest first. Versions follow
[semantic versioning](https://semver.org). The plan for upcoming versions is in
[docs/release-plan.md](docs/release-plan.md).

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
