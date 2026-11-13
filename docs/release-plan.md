# Release plan

From what exists today (a collector and a pipeline) to a full 1.0.0 site at
howlate.la. Each version is one GitHub milestone with a goal, a list of PRs, and
a finish line.

## How every change ships

Every PR follows the `ship-a-change` process:

1. Open an issue in the version's milestone.
2. Create a branch named `v0.X/short-name`. Never work on `main`.
3. Build with tests. Keep each PR under about 400 lines.
4. Run `verify-before-pr`. It runs the real checks, then a fresh-context
   reviewer runs `pr-review` at the depth the risk tier calls for.
5. Answer every finding with `address-review-findings`. Stop after three
   rounds and rethink the approach if Important findings remain.
6. Write the PR description with `git-messages`. You approve it, CI is green,
   and then you merge.

### Risk tiers in this repo

These go into `REVIEW.md` in 0.1.0.

| Tier | What it covers | Review |
|---|---|---|
| High | Anything in `collector/`, because a minute not recorded is gone for good. CI workflows. Bucket lifecycle rules and permissions. Anything that deletes or rewrites data in either bucket. Parquet schema changes. | Deep review, and you read the diff yourself before merge |
| Medium | Pipeline logic, `aggregate` output, the data contract, how the site loads data | Standard review |
| Low | Copy, styles, docs | Quick review |

### Releasing a version

1. Close or move every issue in the milestone.
2. Add a `CHANGELOG.md` entry, written as release notes per `git-messages`.
3. Bump the versions in `pyproject.toml` and `package.json`.
4. With the owner's approval, merge `release/vX.Y.Z` into `main`. Every step
   below runs after this merge, because deploys take their code from `main`.
5. Tag `vX.Y.Z` on `main` and publish a GitHub release.
6. If the release changed anything in `collector/`, redeploy the VM with the
   command in `collector/deploy/README.md`, then watch it:
   - Both feeds log `connected`.
   - The first new file finishes and leaves the spool, about six minutes after
     the restart, holding records from both feeds.
   - healthchecks.io stays up until the fourth file after the restart finishes,
     about 21 minutes. A feed that drops after the first file is only alarmed
     after three more files with nothing from it.
   - Measure the gap as the v0.1.0 notes did: the last record in the file the
     stop signal closed, against the first record after the restart. Add both
     timestamps and the gap to the release notes. v0.1.0 lost 5.7 seconds.
7. If any of those checks fail, roll back first and fix later. Run the same
   deploy command with `reset --hard vX.Y.Z` set to the previous release tag in
   place of `origin/main`, confirm both feeds reconnect, then revert the change
   on `main` through a PR.
8. A release that changed nothing in `collector/` does not touch the VM.
9. The pipeline from 0.3.0 and the site from 0.4.0 deploy on their own when
   `main` changes. Those versions build that, and neither can lose collected
   data.
10. Spend 15 minutes on what the reviews kept finding, and turn repeat findings
    into a lint rule or a `REVIEW.md` line.

Fixes between milestones ship as patch versions, such as 0.5.1.

### Tests are the finish line

A version is complete when every test in its list passes. Each list has three
kinds:

- Functional tests check that the code computes the right answer on known
  input.
- Behavioral tests check that the system acts right over time and when
  something fails: reruns, restarts, missing data, outages.
- UI/UX tests check that a person gets the answer, on a phone and a laptop, in
  light and dark, with a keyboard and a screen reader.

Tools:

- pytest for both Python packages, with small hand-built fixture days in
  `pipeline/tests/fixtures/`. Each fixture has its expected answer worked out
  by hand.
- JSON Schema tests for every file the pipeline hands to the site.
- Playwright for browser flows, run at 375 px and 1280 px wide, in both themes.
- axe-core for accessibility and Lighthouse CI for performance budgets.
- Screenshot comparisons for every chart.

A test added in one version stays in CI from then on, so later versions cannot
quietly break earlier ones. Some checks cannot run in CI, such as live
infrastructure or watching a person use the site. Those are marked "manual",
and their results go in the GitHub release notes.

## 0.1.0 Foundation

Goal: the repo tells the truth, and every later PR has a safety net.

- Fix the README: the pipeline status, the typos, the cost claim, and a link
  to this plan. Badges wait until there is something worth a badge. (Low)
- Add `CLAUDE.md` and `REVIEW.md` for the repo, with the tiers above and what
  failure looks like here: a wrong delay, or a lost minute of collection. (Low)
- Add ruff for linting and formatting in both packages, and fix what it finds.
  (High, because it touches `collector/`)
- Add a GitHub Actions workflow that runs ruff and the collector tests on every
  PR, and require it on `main` and on every `release/*` branch, since feature
  PRs merge there first. (High, because it is a CI workflow)
- Start `CHANGELOG.md` with 0.1.0 describing the collector and pipeline as they
  are, and tag it.

### Tests

#### Functional

- The existing collector tests pass in CI.
- `ruff check` and `ruff format --check` pass on both packages.

#### Behavioral

- A throwaway PR into a release branch that breaks a test cannot merge.
- A direct push to `main` or to a release branch is rejected.

#### UI/UX

- Every command in the README works as written on a fresh clone. (Manual)
- Every README link resolves.

Done when CI is green on `main` and `v0.1.0` exists.

## 0.2.0 Arrivals v2

Goal: `arrivals` keeps everything the site will need, so the 95 GB backfill runs
once.

Checked against a raw file from 2026-11-04: every message carries the vehicle ID,
latitude, longitude, bearing and speed. Every trip is marked `SCHEDULED`. Metro
never flags a cancellation, so ghost trips have to be inferred from trips that
never appear.

- Add pipeline tests on a small hand-built day before changing anything. Cover
  the three-partition service day, origin departures, the approach fallback,
  and the never-observed last stop. (Medium)
- Add `vehicle_id` and `departure_time` (the last `STOPPED_AT`) to each arrival
  row. Bunching, dwell time and early departures all need them. (Medium)
- Add a trips table with one row per scheduled trip: first seen, last seen,
  vehicle, and stops observed. Ghost trips come from this. (Medium)
- Write v2 under `arrivals/v2/`, keep v1 readable, and add checks for the new
  columns to `report.py`. (High, because it changes the stored layout)
- Run v2 on a few days and compare its delays to v1. Record the result in the
  pipeline README.

### Tests

#### Functional

All of these run on the fixture day.

- A trip that starts at 23:50 and runs past midnight lands on the right
  service date, even though half its messages sit in the next UTC partition.
- A scheduled time of `25:30:00` becomes 01:30 on the next calendar day, not
  01:30 on the same day.
- At the first stop, the time is the last `STOPPED_AT` and the row is labeled
  `origin_departure`.
- Mid-route with several `STOPPED_AT` messages, the arrival is the first one
  and `departure_time` is the arriving vehicle's own last one.
- With only `IN_TRANSIT_TO` messages, the arrival is the last one and the row
  is labeled `approach`.
- A stop with no messages still has a row, with an empty delay and source
  `none`.
- `vehicle_id` matches the messages. A trip whose vehicle changes partway has
  one defined, tested outcome.
- In the trips table, a trip with no messages shows as never seen, and a
  partly observed trip counts its observed stops correctly.
- A date on either side of a timetable change picks the timetable that was in
  force that day.

#### Behavioral

- Rerunning a day replaces only that day, and the output rows are identical.
- On the same real day, v2 delays equal v1 delays exactly. (Manual, run on
  three days, results recorded)
- `report.py` flags a fixture with absurd delays.
- A download killed halfway leaves no file that the next run trusts.

#### UI/UX

- Every command in the pipeline README runs as written.

Done when every test above passes.

Out of scope: positions for the replay. The raw archive keeps them, and 0.9.0
reads them with a separate job.

## 0.3.0 Backfill, daily runs, cold storage

Goal: every collected day is graded, every new day is graded without anyone
doing it, and the storage bill stops growing.

- Package the pipeline as a container. (Medium)
- Add a backfill command that grades a date range, can resume after a stop, and
  skips days already done. (Medium)
- Run the backfill. Decide where first. A test download on 2026-11-09 ran at
  37.5 MiB/s, so running locally takes about 45 minutes of download and costs
  about $11. A temporary VM in us-west1 reads for free.
- Add a daily job (Cloud Run job plus Cloud Scheduler, early morning Pacific)
  that grades yesterday, runs `aggregate`, pings healthchecks.io, and alarms on
  a missing day. (High, because it is infrastructure)
- Deploy the pipeline image to the Cloud Run job from GitHub Actions whenever
  `main` changes, so a merged pipeline fix reaches the next daily run. (High,
  because it is a CI workflow with cloud permissions)
- Add the lifecycle rule to the repo, and apply it only after the backfill: raw
  positions move to Coldline after 30 days and Archive after 365. (High,
  because it changes billing)
- Save each day's `report.py` numbers as JSON in the derived bucket. The
  behind-the-scenes page reads them later. (Low)

### Tests

#### Functional

- The backfill grades every day in a range exactly once, skips finished days,
  and picks up where it left off after being killed.
- The container runs the whole pipeline on the fixture day.
- A test parses the lifecycle file and checks the ages, the storage classes,
  and that only `vehicle_positions/` is affected, never `gtfs/`.

#### Behavioral

- A merge to `main` that changes `pipeline/` updates the Cloud Run job's image
  digest, and the next run logs the new version.
- Triggering the daily job by hand grades yesterday, updates the site files,
  and pings healthchecks.io.
- Pointing the job at a day with no raw data raises the alarm.
- A run that crashes before publishing leaves the previous site files
  untouched. A day that fails sends /fail, and the site is still rebuilt from
  the days that finished.
- After the backfill, the number of graded days equals the number of raw days.
  Every day passes the `report.py` ranges or has a written note.
- After the lifecycle rule, files older than 30 days show Coldline, new files
  stay Standard, and the collector heartbeat stays up for 24 hours. (Manual)
- Three days in a row are graded with no manual step. (Manual)

#### UI/UX

- None. Nothing in this version is user-facing.

Done when every test above passes and the new monthly cost is written down.

## 0.4.0 Site skeleton

Goal: an empty but finished-looking site deploys from `main` to a preview URL
and reads real data.

Decisions in this version: the web stack, the chart library, and how data
reaches the site.

Decided: SvelteKit with `adapter-static`, Tailwind CSS v4 with shadcn-svelte for
components, and Observable Plot for charts. Data reaches the site through
Cloudflare R2. The daily job copies each published run there, and the browser
fetches the JSON at runtime, so a new day of data needs no rebuild.
`gs://howlate-derived` never serves the site, because Cloud Storage egress
costs $0.12/GB.

- Scaffold `web/` with SvelteKit, Tailwind, and shadcn-svelte, write the stack
  decision in `web/README.md`, and set up a Cloudflare Pages preview deploy for
  every PR. (Medium)
- Build the design system: type, color tokens for light and dark as Tailwind
  `@theme` variables that the charts also read, Metro line bullets and colors,
  spacing, and a layout grid for phone and desktop. (Low)
- Write a JSON Schema for every file `aggregate` produces, generate TypeScript
  types from it, and add a CI test that fails when pipeline output stops
  matching. (Medium)
- Copy each run to R2 after the daily `aggregate` run, with `current.json`
  written last, so the site reads the new day without a rebuild. (Medium)
- Build the chart pieces with Observable Plot: heatmap, line chart, and
  distribution strip, each checked at 375 px wide and in dark mode. (Medium)

### Tests

#### Functional

- Every file `aggregate` writes validates against its schema, and the generated
  TypeScript types build.
- Renaming a field in `aggregate` without updating the schema fails CI. Prove
  this once on a throwaway branch.
- A heatmap fixture with one hot cell at Friday 17:00 draws that cell in the
  right place.

#### Behavioral

- Every PR gets a preview URL, and `main` deploys.
- After the daily job runs, the preview shows the new last day.
- A missing or broken data file shows an error state, not a blank page.

#### UI/UX

- Screenshot comparisons for every chart at 375 px and 1280 px, in light and
  dark.
- Every color pair meets WCAG AA contrast in both themes.
- The theme follows the device setting.
- No page scrolls sideways at 375 px.

Done when the preview URL shows `status.json` numbers that change every day.

## 0.5.0 First launch

Goal: howlate.la is live with line pages and the engineering story. This is the
version to link on applications.

- Extend `aggregate`: on-time rate by Metro's definition, an all-day delay per
  stop, and a network-wide hour-of-week profile. (Medium)
- Build line search and the line page: hour-of-week heatmap, delay along the
  route, and headline numbers. (Medium)
- Build the reliability ranking page. (Medium)
- Build the behind-the-scenes page: architecture diagram, live status from the
  daily report and healthchecks.io, problems solved, and a cost breakdown from
  real billing. (Low)
- Write the methodology page. Coverage gaps are explained here and nowhere else.
  (Low)
- Add page titles and social preview images, and point the howlate.la DNS at
  Cloudflare. (Medium)

The homepage in this version is a placeholder with the network headline and
search. The story and the replay come in 0.9.0.

### Tests

#### Functional

- On-time rate edges: 61 s early counts as early, 60 s early is on time, 300 s
  late is on time, and 301 s late is late. Check this against Metro's published
  wording first.
- For three lines, the line-page numbers equal a DuckDB query run directly on
  the arrival rows.
- The ranking order equals a sort by the metric it claims, with stable ties.
- Searching "720", "720 rapid", "e line" and "expo" finds the right line. Text
  that matches nothing shows a no-results message.

#### Behavioral

- Playwright opens the page for every line in `index.json`, and all of them
  load without errors.
- A line with little data, or with only one direction, renders without broken
  charts.
- An unknown line URL returns the 404 page.
- The behind-the-scenes status turns to a warning when the newest graded day is
  more than two days old. Test this with a stale fixture.

#### UI/UX

- On a 375 px screen, a scripted user goes from the homepage to the 720's
  Friday 5pm lateness in three taps or fewer.
- Three people see the homepage for five seconds and say what the site is for.
  (Manual)
- axe finds zero serious issues on every page type.
- Lighthouse on mobile scores at least 90 for performance and 95 for
  accessibility, enforced in CI.
- Heatmap values can be read without color: they show on tap, and a table
  version exists for screen readers.
- Search and charts work with a keyboard alone.
- Social previews render correctly. (Manual)

Done when every test above passes.

## 0.6.0 Commute tool

Goal: "I ride the 720 from Wilshire/Vermont to Westwood. I leave at 8:00, or I
need to arrive by 9:00. Which bus, how long, how late?"

- Build a trip-pattern summary. Trip IDs change with every timetable (they end
  in a suffix like `-JUNE26`), so key each trip by route, direction, day type
  and scheduled start time. For each pattern and stop, store the spread of
  actual times across all days. Key it by stop as well as by line so transfers
  fit later without a reshape. (Medium)
- Compute ride time from stop A to stop B for each pattern, from arrivals on
  the same trip. (Medium)
- Add stop search by name and nearest stop by location. (Medium)
- Build the commute screen: line, from, to, and a Leave at / Arrive by toggle.
  It answers how late it usually is, how bad it gets, which bus to catch to be
  on time 9 times in 10, and how long the ride takes. (Medium)

### Tests

#### Functional

- A fixture with two timetable versions maps the weekday 7:42 departure from
  both versions to one pattern.
- Ride time from A to B uses arrivals from the same trip only. A "to" stop that
  comes before the "from" stop on the route is rejected.
- "Arrive by 9:00" picks the latest departure whose 9-in-10 arrival is at or
  before 9:00. Test the boundary minute.
- "Leave at 8:00" picks the first scheduled departure from A at or after 8:00.
- Weekday, Saturday and Sunday each use their own patterns, and a trip after
  midnight belongs to the day it started.

#### Behavioral

- Five real commutes are checked by hand against the arrival rows. (Manual,
  recorded)
- A stop with too few observations says "not enough data" instead of showing a
  number.
- A stop served in only one direction cannot be picked the wrong way.
- If location access is denied, the tool falls back to search.
- The commute lives in the URL, so a shared link shows the same answer.

#### UI/UX

- Three people each set up "720, Wilshire/Vermont to Westwood, arrive by 9:00"
  on a phone in under 30 seconds. (Manual, timed)
- Switching between Leave at and Arrive by keeps the chosen stops.
- The answer appears first as a plain sentence, and the chart comes after it.
- A screen reader reads the answer sentence.

Done when every test above passes.

"How long will I wait" arrives in 0.7.0, because it needs bunching.

## 0.7.0 Reliability patterns

Goal: show the behavior that lateness alone hides.

- Measure bunching: the real gap between consecutive buses at a stop against
  the scheduled gap, and excess wait time. The commute tool gains "how long will
  I wait". (Medium)
- Find ghost trips: scheduled trips never seen in the feed. Label them "not
  seen" rather than "cancelled", because the feed cannot tell an untracked bus
  from one that did not run. (Medium)
- Find early buses: departures more than one minute early, by Metro's
  definition. (Medium)
- Measure schedule padding: scheduled time between stops against the observed
  median, by segment and time of day. (Medium)
- Add a patterns section to the line page and a network patterns page. (Medium)

### Tests

#### Functional

- Buses at 8:00, 8:02 and 8:20 on a route scheduled every 10 minutes give gaps
  of 2 and 18 minutes, and an excess wait equal to a value worked out by hand.
- A trip with zero messages counts as a ghost trip. A trip with one message
  does not.
- A departure 61 s early counts as early, and 60 s early does not.
- A segment scheduled at 6 minutes with an observed median of 4 shows 2 minutes
  of padding. A segment where buses need more time than scheduled shows
  negative padding.

#### Behavioral

- When the feed drops for an hour, the trips in that hour are not counted as
  ghost trips. A fixture with a gap in the collector files proves this. Without
  this check, every collector outage would look like Metro cancelling buses.
- Each new metric has a range check in `report.py`.
- The commute tool's wait time agrees with the gap numbers for the same stop.

#### UI/UX

- Two people who are not engineers read each pattern's one-sentence
  explanation and can say what it means. (Manual)
- No page uses the word "cancelled" for a ghost trip. A text test checks this.
- Screenshot comparisons for every new chart.

Done when every test above passes and every new metric has a methodology entry.

## 0.8.0 Power users

Goal: people can ask their own questions.

- Publish the data on Cloudflare R2, which has no download fees, with documented
  endpoints, a license, and Metro attribution. (High, because it makes a bucket
  public)
- Query per-line Parquet files in the browser with DuckDB, which is what makes
  free-form filters possible. (Medium)
- Add filters: date range, weekday or weekend, direction, and excluding
  holidays. (Medium)
- Compare lines side by side. (Medium)
- Show trends: weekly series per line and for the network, marking timetable
  changes, which the collector already records. (Medium)

### Tests

#### Functional

- Every public file matches its documented schema.
- The example query on the docs page runs in CI and returns the expected rows.
- For the same filter, a query in the browser returns the same result as DuckDB
  on the server.
- Date-range edges are inclusive, and excluding holidays removes exactly the
  listed dates.
- Download checksums are published and match the files.

#### Behavioral

- Anyone can read the R2 bucket, and nobody without credentials can write to it.
  Test both.
- A large filter on a throttled phone connection shows a loading state, can be
  cancelled, and never freezes the page.
- Trend charts mark timetable changes on the right dates.

#### UI/UX

- Two lines compared side by side share the same axis scale.
- Filters live in the URL, and the back button undoes them.
- An engineer who has never seen the site runs a query from the docs page alone.
  (Manual)

Done when every test above passes.

## 0.9.0 Replay and story

Goal: the signature visual, the homepage story, and a polish pass. This is the
release candidate.

- Build the replay data job. For a few chosen days, sample each vehicle every 30
  to 60 seconds from the raw positions, color by delay from the arrival rows,
  and write compact binary files per hour. About 1,500 vehicles are on the road
  at once at midday. Reading those days from cold storage costs a small fee, so
  pick the days once. (Medium)
- Add a base map from open vector tiles hosted on R2, so there is no API key and
  no per-view bill. (Medium)
- Build the replay player: a day in 60 seconds, with play, pause and scrub,
  within a performance budget for phones. (Medium)
- Build the homepage: your story, the replay, and the headline. (Low)
- Polish: accessibility audit, performance budget, error and empty states, a
  404 page, and a full pass on a phone and a laptop. (Low to Medium)

### Tests

#### Functional

- For 20 sampled vehicles, replay positions sit within a set distance of the
  raw positions at the same moment.
- A vehicle's replay color matches its trip's delay at that moment.
- The binary files decode back to exactly what was encoded.

#### Behavioral

- Each hour file stays under its size budget, about 1 MB. The first frame shows
  within 2 seconds on a throttled 4G connection.
- Scrubbing to any time shows the right clock and the right vehicles.
- With the device's reduced-motion setting on, the replay does not autoplay.

#### UI/UX

- The replay holds about 50 frames per second on a mid-range phone. (Manual)
- Every page gets a full pass on a phone and a laptop, in both themes, from a
  written checklist. (Manual)
- The homepage story passes an `unslop` review.
- Screenshot comparisons for the 404, error and empty states.

Done when every test above passes.

## 1.0.0 Launch

Goal: complete, stable, and announced.

- Freeze the data contract and public endpoints as v1. A breaking change after
  this means 2.0.0.
- Reach 30 days of daily runs with no manual fix.
- Rewrite the README around the live site, with screenshots and final resume
  bullets.
- Announce it on your portfolio, LinkedIn, and LA transit communities.
- Hold a retro on the whole project.

### Tests

#### Functional

- Every test from 0.1.0 to 0.9.0 is green on `main`.
- A CI check fails on any breaking change to the v1 schemas. Added fields pass,
  and removed or renamed fields fail.

#### Behavioral

- The daily job log shows 30 runs in a row with no manual fix.
- Recovery drill: in a test copy of the derived bucket, delete the site files
  and rebuild them from the arrival rows with one command. Then delete one day's
  arrival rows and regrade that day. (Manual)

#### UI/UX

- Three riders and two engineers each finish one task on their own. Everything
  they get stuck on is fixed or logged. (Manual)

Done when every test above passes.

## After 1.0

- 1.1: transfers in the commute tool.
- Alerts for a saved commute.
- Live "right now" view.
- Other LA agencies that publish the same feed formats, such as Big Blue Bus.
