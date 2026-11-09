# Changelog

Every release of HowLate, newest first. Versions follow
[semantic versioning](https://semver.org). The plan for upcoming versions is in
[docs/release-plan.md](docs/release-plan.md).

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
