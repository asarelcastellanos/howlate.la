# Changelog

Every release of HowLate, newest first. Versions follow
[semantic versioning](https://semver.org). The plan for upcoming versions is in
[docs/release-plan.md](docs/release-plan.md).

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
