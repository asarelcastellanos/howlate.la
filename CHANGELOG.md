# Changelog

Every release of HowLate, newest first. Versions follow
[semantic versioning](https://semver.org). The plan for upcoming versions is in
[docs/release-plan.md](docs/release-plan.md).

## 0.5.1 - 2026-11-17

Launch fixes. Every line page now has its own title and link preview in the
served HTML, the ranking panels and sorts are corrected, the home page keeps
working when the status file fails, and the rail on-time share is shown with a
note on how HowLate measures it. Only the site changed.

### Added

- Line pages are prerendered, one page for each of the 115 lines. Each has its
  own title, description and canonical link in the served HTML, so a crawler or
  a link preview that does not run JavaScript sees them. The titles come from
  `web/src/lib/data/lines.json`, which is committed. `npm run lines:refresh`
  rewrites it, and the line rules in `_redirects`, from the published index. A
  line that is not in the file still works in the browser, with the shell and no
  title.
- One `/lines/<id> /lines/<id> 200` rule per line in `web/static/_redirects`,
  ahead of the wildcard rule. The wildcard alone served every line the same
  1,508-byte shell, and a `.html` target looped with a 308. On the branch
  preview, `/lines/720` and `/lines/2` returned their own title, description and
  canonical link, and `/lines/zzz` still got the shell (#156).
- A "How we measure on-time" section on the methods page. It says what HowLate
  scores, why it scores every measured stop after the first, what the feed
  gives at the last stop, and what Metro's standards say. It does not claim the
  gap to Metro's 99.4 percent for rail is explained. A sentence under it gives
  the network bus and rail shares from the published data.
- A footnote beside every on-time share, short on a phone and in full on a wider
  screen, with a link to the methods page. Both forms say Metro reports
  on-time performance differently.
- An On time column in the rail table on the ranking page. Rail lines are listed
  there and are not ranked against buses.
- Two Playwright cases for the home page's Try again button, and tests that
  check the footnote at 375 and 1024 px and find each mark by `data-testid`.
- `web/tests/testScript.test.ts`, which checks that every test file named in the
  `test` script exists and that every test file is named.

### Changed

- The rail on-time share is shown. `SHOW_RAIL_ONTIME` is now true, so the
  ranking page and the line pages show it. This reverses the 0.5.0 decision on
  #133 to keep it hidden. The decision is recorded in #157. HowLate's rail share
  is 64.4 percent against Metro's 99.4 percent, and the methods page says the
  gap is not explained.
- With 10 or fewer ranked lines, the Least reliable caption states the real
  count, and the panel is hidden when it would be empty (#158).
- The median and 90th percentile columns on the ranking page sort by distance
  from the on-time window, -60 to +300 seconds, and then by the size of the
  delay. Every bus median on 2026-11-16 was inside the window, so the second key
  keeps the sort useful. The sort arrow still points up, which is only
  approximately right, because an early value can now rank below a late one
  (#158).
- A share under 100 prints as at most 99.9 on the line headline and the ranking
  page. Exactly 100 still prints 100.0 (#158).
- On the home page, a failed `status.json` no longer hides the search box. Each
  file keeps its own result (#161).
- The behind-the-scenes page no longer says a cost breakdown will be published.
  It keeps the budget figure and says it is an estimate (#159).
- The web README and code comments that the ranking and line page changes made
  wrong are corrected.

### Fixed

- The home page's status and index error views lost their Try again button when
  only one of the two files failed. #161 dropped it, the review found it, and
  #168 restored it with two Playwright cases that fail without the change.
- A typo in the web `test` script left two test files out of the run, about 15
  tests. The new `testScript.test.ts` fails if a test file is missing from the
  script.
- Line pages in 0.5.0 had no title, description, canonical link or Open Graph
  tags in the served HTML. They have them now, as described under Added.

### Checked

- The pipeline's 512 tests pass. The web's 264 tests pass. The web had 210
  tests in 0.5.0.
- Playwright passes 32 of 32 against the fixture build. It had 26 in 0.5.0.
- Lighthouse performance on `/lines/720` is 0.96 against a threshold of 0.9.
- The release got a review, and its findings are fixed. The home page retry, the
  footnote tests and the copy about Metro came from it, and `LESSONS.md` has an
  entry for each.

### Known gaps

- HowLate's rail on-time share is 64.4 percent and Metro's is 99.4 percent. The
  gap is not explained. Matching to the schedule accounts for at most 0.9
  points, the timestamp lag is about 7 seconds, and scoring departures gives
  the same share.
- Metro's policy says bus is measured at timepoints and rail at the end terminal
  on arrival. It states no on-time window for rail, so HowLate uses the bus
  window of -60 to +300 seconds for rail.
- Coverage is 71.35 percent for bus and 88.27 percent for rail. Most of the gap
  is bus stops the feed skipped between two reports (#165).
- The site shows data that is two days old on purpose, to leave a margin for the
  daily job (#164).
- A line that Metro removes or renames stays live until `npm run lines:refresh`
  is run again and the result is committed and deployed. A page at
  `/lines/<id>/`, with a trailing slash, gets the shell with no title.
- The 99.9 cap never fires on published data. The pipeline rounds to one
  decimal and the files carry no on-time count, so 99.96 arrives as 100.0. The
  rounding is left for a later release.

### Not changed

- The collector stays at 0.1.0, and the VM is not redeployed.
- The pipeline and its published JSON are unchanged.

## 0.5.0 - 2026-11-17

The first launch. howlate.la shows a page for every line, a reliability
ranking, a methodology page and a behind-the-scenes page with live status. The
pipeline adds an on-time share and the files those pages read. CI now opens
the home page, every fixture line page, the ranking, the methodology page and the
behind-the-scenes page in a browser.

### Added

- Line search on the home page. It finds `720`, `720 rapid`, `e line` and
  `expo`, works from the keyboard alone, and shows a message when nothing
  matches.
- A page for every line at `/lines/<line>`. Each direction shows the median
  delay, the 90th percentile, the measured arrivals and the on-time share. A
  direction switch appears when a line has two. An unknown line shows a
  not-found message.
- The line page has four charts. The heatmap, the week chart and the stop strip
  from 0.4.0 are joined by a route chart. It shows each stop's all-day median
  delay in route order, with the 90th percentile as a lighter line, and it
  breaks the line at a stop that was never measured, not at zero. A hidden table
  lists every stop for screen readers.
- Each heatmap cell can be read by tap, hover or keyboard. A readout under the
  heatmap gives the day and hour, the median delay, the on-time share and the
  arrivals measured. The grid is one tab stop. Arrow keys move the selection,
  and Home and End go to the first and last hour of the day. A thin hour says
  there are too few arrivals to judge, and an empty hour says nothing was
  measured.
- A reliability ranking at `/ranking`. Bus lines are ranked by on-time share.
  The page lists the five most and five least reliable lines, and a table that
  sorts by on-time share, median delay or 90th percentile from the keyboard. A
  line needs 500 measured arrivals to be ranked. In the data at the time, only
  line 697, the SoFi shuttle, fell below, with 202 arrivals. The next smallest
  line had 18,078. Lines under the floor are listed with their counts. Rail
  lines are in a separate table with median and 90th percentile only.
- A methodology page at `/methods`. It explains how a delay is measured, what
  counts as on time, why some stops have no number, how the daily checks work
  and what HowLate does not know. Coverage gaps are explained there and nowhere
  else. It gives Metro's own on-time window and its bus figure of 78.2 percent
  for July to September 2025, and says that figure is measured at timepoints, so
  it is not comparable.
- A behind-the-scenes page at `/behind-the-scenes`. A status panel reads
  `health.json` and shows the newest graded day, whether its checks passed, its
  coverage and a 14-day strip. The strip uses a check, a cross or a dashed
  outline, not color alone. The panel turns to a warning when the newest graded
  day is more than 3 days old in Los Angeles. The daily job runs at 5 am Pacific
  and grades 2 days back, so the newest day is 3 days old for about 5 hours
  every night, and exactly 3 days is not a warning.
  If `health.json` is missing or in the old shape, the page says the status is
  not published yet. An inline diagram with a text list shows the path from
  Metro's feeds to the site, and six problems solved come from this changelog,
  `LESSONS.md` and the git history. The cost is labelled an estimate, with the
  budget figure and no breakdown.
- A main navigation on every page, with a skip link first in tab order. Every
  prerendered page has its own title and description, a canonical link, and Open
  Graph and Twitter tags in its HTML. Line pages are drawn in the browser, so
  they set these when the page loads, and the served HTML has none. The design page is marked `noindex`. A 1200 by 630 social
  preview image is 60 KB. A build test checks every prerendered page for one
  `h1`, a unique title and description, the tags and the navigation.
- An on-time share in the pipeline. On time means a delay from -60 to +300
  seconds, inclusive at both edges. That is Metro's published window, 1 minute
  early to 5 minutes late. The field is called `ontime`, and its description
  says it is not Metro's published figure, because HowLate scores every stop and
  Metro scores timepoints and rail terminals. The profile hours, each stop's
  all-day numbers, the directions, the lines and the index entries carry it.
  The index also carries each line's `n`, `med`, `p90` and `pct5`, so the
  ranking page sorts without opening 115 files.
- `network.json`, the hour-of-week profile for the whole network, split into bus
  and rail, with all-day headline numbers.
- `health.json`, built from the newest 14 saved daily reports. It holds the
  pipeline version, the newest graded day, one entry per recent day and the
  newest day's checks with their labels. Each field is picked by name, so the
  rest of a report cannot reach the public file. A test puts a `gs://` path, an
  endpoint, an email address and a host in a report and checks that none
  appears. It reads every report shape in the bucket, including 0.3.0 reports
  with the old `join_rate` name. A day with no report is left out, and an
  unreadable report is skipped with a log line. The daily job now downloads 14
  reports, about 42 KB, each run, and `aggregate` takes a `--reports` folder for
  local runs.
- A strict JSON Schema, a generated type and a loader with a shape check for
  `network.json` and `health.json`. The schemas for the profile, the stops, the
  lines and the index gain the on-time fields.
- A `browser` CI job that `all-checks` waits on. It builds the site against a
  committed fixture of eight lines in the current data shape. They cover two
  directions, one direction, little data, a rail line, a Rapid line and a
  busway, each cut to 10 stops per direction. A pipeline test checks the fixture
  against the strict schemas.
  - Playwright opens every fixture line at 375 px. It fails on a console error,
    a missing or second `h1`, an error state or a sideways scroll. It also
    checks the not-found message, search, the ranking, the Friday 5 pm readout,
    that rail pages show no on-time sentence, and that the behind-the-scenes
    page shows the newest day, a 14-day strip with its failed day marked, and
    a warning when the newest day is 4 days old.
  - axe fails on any serious or critical issue on the home page, a line page,
    the ranking, the methodology page and the behind-the-scenes page, in light
    and dark.
  - Lighthouse on mobile, with the median of 3 runs, must score 90 for
    performance and 95 for accessibility on the home page, a line page and the
    ranking.
  - Playwright 1.64.1, axe-core/playwright 4.14.0 and Lighthouse CI 0.16.1 are
    pinned exactly, and the actions are pinned by commit SHA. The job uses no
    secrets and has read-only permissions.
- The site is served at https://howlate.la, and `www.howlate.la` redirects to
  it. The data is served at https://data.howlate.la, a custom domain on the R2
  bucket.

### Changed

- A trip counts as explained only when every timetable copy compared lists it
  under a service that starts after the day. That was the one cause measured on
  2026-11-07, 11-13 and 11-14. A service that expired, a service that a
  `calendar_dates` row removed and a service with no calendar row stay
  unexplained and fail `matched_rate` again.
- A new check, `explained_lines`, fails when a line has at least 5 observed
  trips and every one is explained. The 5 percent cap on `explained_pct` is
  network-wide, so it could not see one small line hidden whole. The floor of 5
  is a judgment, and the code says so. Regrading 2026-11-14, 11-13, 11-12,
  11-07 and 10-31 locally gives the same counts as before, 338, 244, 0, 214 and
  0 explained trips, and every check passes.
- The default data address in `web/src/env.ts` is `https://data.howlate.la`, and
  the site's canonical and preview links use `https://howlate.la`. A test pins
  both. The pipeline and web docs, the `daily.sh` prompt and the release plan
  name the new addresses. The validation rules for the public address do not
  change.
- CORS on the data stays open. The data is public and read only, and the
  `pages.dev` preview deployments need it. This differs from #121, which asked
  to tighten it, and both READMEs record why.
- `upload` publishes only the site files a run built, and `build` returns their
  names. Before, `upload` published every `.json` file in the directory. A line
  Metro had dropped could come back from an old file on a reused disk, and a
  test shows the old code did it. Stray files in the directory are neither
  uploaded nor deleted.
- `yesterday()` and the R2 freshness check read the calendar day from the
  Pacific clock through one helper, `pacific_today`. Before, `yesterday()` read
  the machine clock, which is UTC on Cloud Run. A run started between 16:00 and
  24:00 Pacific, such as a manual run, saw the next UTC date. The scheduled
  05:00 Pacific run is unchanged. The run-name timestamp stays UTC, because it
  names no calendar day.
- Rail on-time share stays hidden. The decision on #133 is that HowLate does not
  show one yet, because it measures 64.4 percent for rail against Metro's 99.4
  percent, and times the last stop of 84 percent of rail trips from the last
  report before the train arrived. Rail lines show the median and 90th
  percentile delay. One constant, `SHOW_RAIL_ONTIME`, turns the share on later,
  and the ranking and the line pages follow it. The methodology page says this
  in plain words and no longer quotes Metro's rail figure.

### Fixed

- Chart labels failed axe with 13 serious `aria-prohibited-attr` nodes on a line
  page, in light and dark. Observable Plot puts an `aria-label` on inner groups
  that have no role. `Chart.svelte` removes those labels after each render, and
  the labels on the chart container and on groups with a role stay. After the
  change axe finds none. The heatmap found its cells by those labels, so it now
  sets its own `howlate-cell` class. A test draws the four charts, fails if a
  group with no role keeps a label and checks that all 168 heatmap cells are
  still found.
- The arrivals docstring said the last stop of a trip is never observed. The
  rail analysis in #133 found it is timed from the last approach report in 84
  percent of rail trips and 64 percent of bus trips, an estimate with almost no
  stopped reports. The docstring says that now, and so does the comment in
  `report.py` on the `terminus_stopped` check, which now says the check found
  none on the days checked.
- The week chart's axis label no longer overlaps its top tick, and the design
  page no longer calls route 4 a local route.

### Checked

- The pipeline's 441 tests, the collector's 5, ruff lint and ruff format pass.
  The pipeline had 385 tests in 0.4.1.
- The web type check, lint and build pass, and so do 210 web tests. Five more
  tests read a git-ignored local data folder and skip when it is absent. The web
  had 28 tests in 0.4.0. `npm run types` leaves no diff.
- Three lines (801, 720 and 4) and the network match an independent DuckDB query
  on 90 days of real data, 51.6 million arrivals. Changing the on-time window to
  +299 or -59 seconds fails 6 tests. The edge tests cover -61, -60, +300 and
  +301 seconds.
- All 115 lines in the index load at 375 px with no console errors, one `h1` and
  no sideways scroll, against local data in the new shape. From the home page,
  tapping the search box, the 720 result and the Friday 5 pm cell shows the
  readout in three taps at 375 px.
- Locally, 26 Playwright tests pass. Lighthouse performance is 1 on the home
  page, 0.96 to 1 on a line page, 1 on the ranking and 1 on the
  behind-the-scenes page, and accessibility is 1 on all four. A deleted line
  file, a renamed field, a raised threshold and a wide element each fail the
  right check.
- Built from the real reports through 2026-11-15, `health.json` is 3.9 KB. The
  newest 14 days all pass, including 2026-11-07, 11-13 and 11-14 under the new
  checks. The three failing days in the bucket are older.

### Known gaps

- The live daily job still has the old `R2_PUBLIC_URL`. It is updated by running
  `pipeline/deploy/daily.sh` again after the owner approves. The `r2.dev`
  address stays on until the new site is live, then gets turned off.
- The data on R2 keeps the old shape until the first daily run after the
  deploy. Until then the ranking page shows a needs-newer-data message and the
  behind-the-scenes page says the status is not published yet, because the
  bucket has no `health.json`. The line pages and the home page were checked
  only against local data in the new shape.
- Lighthouse performance on a line page is 0.96 to 1 locally against a
  threshold of 0.9. The first CI run scored 0.89 before the chart code loaded
  after the headline, so a slow runner can still land a few points below a local
  run.
- Rail on-time share is hidden, as described under Changed.
- Line pages have no title, description, canonical link or Open Graph tags in
  the served HTML, because the browser draws them. A link preview or a crawler
  that does not run JavaScript sees none of them for `/lines/<line>`.
- The Artifact Registry cleanup (#124) is not done.

### Not changed

- The collector stays at 0.1.0, and the VM is not redeployed.

## 0.4.1 - 2026-11-16

The daily job now alarms when the public site data goes stale. It fails when the
R2 settings are missing and checks the public address after each copy.

### Added

- `R2_REQUIRED` makes a job with no R2 settings fail with the failure ping. It
  no longer skips the copy and pings success. Any value except 0, false, no, off
  or none counts as set, so a typo such as `on` cannot turn the guard off.
- After each R2 copy that moved the pointer, the job fetches the public
  `status.json` through the pointer. The URL carries a changing query, so the 60
  second cache cannot answer. The run fails with the failure ping if the fetch
  fails, if the public pointer is older than the copied run, or if `last_day` is
  more than 4 days before today's date in Los Angeles. The job grades up to two
  days back at 05:00 Pacific, so a gap of 2 is normal.
- With `R2_REQUIRED` set, a missing or invalid `R2_PUBLIC_URL` fails the daily
  run before anything is copied. `publish-r2` does not read it.

### Changed

- The failure ping names every failed day: each day whose grading raised, with
  the first non-empty line of its error cut to 160 characters, and each day that
  only failed its checks or its cleanup. When the 1000 character limit cuts the
  list, the ping ends with `and N more days`.
- The R2 settings errors ("R2 is partly configured; missing ...", an invalid
  endpoint) reach the ping with their text, not just `ValueError`.
  `publish-r2` prints them as one line and exits 1, not as a traceback.
- Before anything goes to healthchecks.io, the job replaces URLs, `gs://` and
  `s3://` paths and email addresses with placeholders, in any letter case, in
  the crash ping too. A bare hostname with no scheme is not replaced.
- `pipeline/deploy/daily.sh` sets `R2_REQUIRED=1` and `R2_PUBLIC_URL` when R2 is
  configured. It refuses to deploy without a public URL, and accepts only
  `https://<hostname>` for it and the endpoint, as `is_https_address` does. The
  public URL prompt no longer offers a skip.

### Checked

- The pipeline's 385 tests and the collector's 5 pass, and so do ruff lint and
  ruff format. The pipeline had 205 tests in 0.4.0.
- The probe passed against the live public R2 address, reading the real pointer
  and status file, with today's date in Los Angeles.

### Not done yet

- After the merge, run
  `R2_PUBLIC_URL=https://<public address> bash pipeline/deploy/daily.sh` once.
  Until then the live job has no outside check and no `R2_REQUIRED` guard.
- A copy that leaves R2's pointer alone because a newer run appeared still pings
  success and is not probed. This is intended.

### Not changed

- The collector stays at 0.1.0, the site at 0.4.0, and the schemas are the same.

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
- A contrast test of 52 color pairs against WCAG AA. The hatch and dotted marks
  are held to 3:1 in both themes. CI runs it.
- Three charts, drawn with Observable Plot. The heatmap shows median delay by
  day and hour. The line chart shows the median and the 90th percentile across
  the week. The strip shows each stop's delay for the weekday evening rush, 3 to
  7 pm. A heatmap hour with fewer than 5 arrivals is hatched, so a two-arrival
  hour is never the worst hour. An hour with nothing measured is dotted, which
  can mean no service or no scheduled stop was measured.
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
  partway leaves R2 on the previous complete run. A successful copy also deletes
  R2 runs the pointer does not list, except the run R2 last named. A failed copy
  exits non-zero and sends the failure ping, and the graded days stay saved.
  Without the three R2 settings, it is skipped.
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

- The pipeline's 205 tests, ruff lint and ruff format pass. The web type check,
  lint, build and 28 tests pass, and `npm run types` leaves no diff.
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

- Reports already in `gs://howlate-derived` keep the old `join_rate` check name
  until those days are graded again.

### Known gaps

- A job with no R2 settings skips the copy and still sends the success ping.
  After the merge, the owner runs `pipeline/deploy/daily.sh` once and checks
  that the first live run logs the copy.
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
