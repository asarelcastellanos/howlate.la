# Changelog

Every release of HowLate, newest first. Versions follow
[semantic versioning](https://semver.org). The plan for upcoming versions is in
[docs/release-plan.md](docs/release-plan.md).

## 0.1.0 - Unreleased

The first tagged version. It names what was already running before versions
existed, and adds the checks every later change goes through.

### Already running

- The collector has recorded both of Metro's live feeds since 18 August 2026:
  all 114 scheduled bus lines and all 6 rail lines, about 25 million records a
  day, shipped to `gs://howlate-raw` every five minutes.
- It saves a copy of Metro's timetables whenever they change, and fails loudly
  when Metro adds or drops a line that is not being recorded.
- It replaces a socket that is open but silent, and raises an alarm through
  healthchecks.io when nothing arrives from either feed.
- The pipeline grades one service day into one row per scheduled stop
  (`arrivals`) and summarises every graded day into the JSON files the site will
  read (`aggregate`). It has been run on 18 and 19 August.

### Added

- `CLAUDE.md`, `REVIEW.md` and the release plan.
- ruff linting and formatting for both packages.
- Issue forms and a PR template.
- This changelog.

### Changed

- The README matches the code: pipeline status, monthly cost, and typos.
