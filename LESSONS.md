# Lessons

Each entry records a mistake the checks or review caught and the lasting fix.

## 2026-11-13: Sampled figures written as whole-day counts
- What happened: three figures in the timetable change (1,396 and 1,337
  distinct trips, and "15 missed") came from sampled raw files and went into
  code comments and the changelog as full-day counts. The full days held 1,413
  and 1,348 distinct trips, and the best copy missed 26, not 15.
- Caught by: the review, where a tests-and-claims finder and three verifiers
  re-read the full days.
- Fix: a rule under "Claims in docs and comments" in REVIEW.md.

## 2026-11-13: A test errored in the container job instead of skipping
- What happened: the drift test for the shuttle lines took
  `Path(__file__).parents[2]`, which does not exist when the tests are mounted
  at `/tests`, so it raised IndexError in the `container` CI job before
  reaching its skip. The author and one finder had both written that it
  skipped cleanly.
- Caught by: the review's verifiers, then reproduced in one line of Python.
- Fix: a "Tests" rule in REVIEW.md, and the test now skips only when
  `collector/` is absent.

## 2026-11-13: Review agents wrote to the raw bucket
- What happened: a verifier ran `gcloud storage cp` with no local destination,
  and gcloud treated the last `gs://` URL as the destination folder. It wrote
  133 objects into the raw archive bucket, which only the collector may write.
  A second agent left an orphaned `gsutil cp` with the same mistake running for
  44 minutes, and the main session stopped it before it wrote. The owner
  approved deleting the 133 copies.
- Caught by: the verifier that reported it, then a check of the bucket by the
  main session.
- Fix: a "Review agents" rule in REVIEW.md, and a hook plus a read-only
  credential for subagents, tracked in
  https://github.com/asarelcastellanos/claude-workbench/issues/26.

## 2026-11-16: A dashboard build variable did not reach the Pages build
- What happened: the site reads its data address from `PUBLIC_DATA_BASE`, which
  was set in the Cloudflare Pages dashboard. The deployed preview did not
  contain it, so the home page showed "We couldn't load this data" while a
  local build with the variable showed real numbers.
- Caught by: loading the deployed preview. No CI check can see it, because CI
  does not build with the dashboard's variables.
- Fix: the public R2 address is the default in `web/src/env.ts`, so every build
  reads real data and a dashboard value only overrides it. A change to where
  the site reads data is not done until the deployed preview shows the numbers.

## 2026-11-16: A copy's guarantee held for a crash but not for a race
- What happened: `r2.publish` promised that R2's pointer never names a partial
  run, and its tests covered a copy that dies partway. A hand-run
  `publish-r2 --run X` during X's upload could finish cleanly and write a
  pointer over 2 of 4 files. A catch-up copy after two failed days deleted the
  run that readers were still on.
- Caught by: the review, where three verifiers reproduced each case with the
  test fakes.
- Fix: both cases now have checks in `pipeline/src/howlate_pipeline/r2.py` and
  tests in `pipeline/tests/test_r2.py`. When a docstring promises an
  invariant, a test must try to break it with a second writer, not only a
  crash.

## 2026-11-17: Two validators for one value disagreed
- What happened: `daily.sh` and `r2.py` each checked the public data address.
  The shell accepted `https://host:443` and `https://host?x=1`, and the Python
  rejected them, so a value could deploy cleanly and then fail every daily run
  after the copy. The Python check also let an embedded newline through.
- Caught by: the review, where three finders each found it and ran both checks
  on the same inputs.
- Fix: both checks now match `https://[A-Za-z0-9.-]+` in full, and
  `pipeline/tests/test_daily_sh.py` runs the shell check and the Python check
  on the same list of good and bad values. When a value is validated in two
  languages, one test must feed both the same inputs.

## 2026-11-17: A freshness check compared the data with itself
- What happened: the probe checked that the public `last_day` was within 2 days
  of the newest graded day, but it took the newest day from the site the same
  job had just built. The public file was that same build, so the gap was always
  0 and the check could never fire, while the docs listed it as a separate
  alarm.
- Caught by: the review, where two finders reasoned about where each side of
  the comparison came from.
- Fix: the probe compares `last_day` with today's date in Los Angeles, and a
  test shows a mutant that reads the gap as always 0 fails. An alarm needs a
  reference that its own run cannot change.

## 2026-11-17: A staleness limit ignored the producer's schedule
- What happened: the site warned when the newest graded day was more than 2
  days old. The job runs at 05:00 Pacific and grades today minus 2, so the
  newest day is 3 days old for about 5 hours every night, and the status page
  showed a false red warning.
- Caught by: three of the five reviewers in the v0.5.0 deep review.
- Fix: the limit is 3 days, with a test that walks a daily cycle (14:00Z,
  07:59Z, 08:00Z, 12:30Z), in PR #152. Derive a staleness limit from the
  producer's schedule and test it at the times of day that schedule creates,
  not only at the boundary.

## 2026-11-17: Tests passed while the code was wrong in seven places
- What happened: the tests reviewer broke the code on purpose and the tests
  still passed for seven changes. They were the link from downloaded reports to
  `health.json`, the 5 percent explained cap (any cap from 0.5 to 16.6 passed),
  a leftover-folder test that used an empty directory and so could not see a
  stale file, a count check's expected value, the pointer prefix check, the
  500-arrival floor (computed from the constant it tested), and a heatmap
  filter.
- Caught by: the tests reviewer, using mutation checks.
- Fix: tests with literal values in #151 and #152, each shown failing against
  its mutant. A boundary test uses a literal number, never the constant under
  test, and a fixture for a leftover must contain the thing that would go wrong.

## 2026-11-17: A browser quality gate sat 0.01 above the local score
- What happened: the new Lighthouse check required a performance score of 0.9
  on a line page. The local run scored 0.92, the first CI run scored 0.89, and
  the release PR failed.
- Caught by: CI on the release PR.
- Fix: the chart code now loads after the headline (#155), and local scores are
  0.96 to 1. Measure a new gate on the CI runner, or leave at least 0.05 of
  headroom, before it can block a release.

## 2026-11-17: The release branch could not merge into main
- What happened: main held the squash commit of the previous release, and the
  release branch held the same changes as separate commits, so GitHub reported
  a conflict.
- Caught by: opening the release PR.
- Fix: the release PR was built on main with the release files and checked with
  an empty diff against the release branch (#154). After a release squash-merges
  to main, bring the next release branch up to date with main in a PR before
  work builds on it, or branch the next release from main.

## 2026-11-17: A hosting setting overrode the code default and broke the site
- What happened: v0.5.0 changed the site's default data address to
  `data.howlate.la`, but the Cloudflare Pages project still had a build variable
  `PUBLIC_DATA_BASE` that pointed at the old `r2.dev` address, so the deployed
  site kept fetching `r2.dev`. Turning `r2.dev` off then made every data page
  show "We couldn't load this data" until the variable was deleted and the site
  rebuilt.
- Caught by: the owner, who saw "try again" on howlate.la. The earlier live
  checks ran before `r2.dev` was turned off and could not see it.
- Fix: the variable was deleted in the Pages settings and the production
  deployment retried, so the code default is the only source. Before turning off
  an old endpoint, load every live page in a browser with the network tab open
  and confirm no request still goes to it, and list the hosting settings that
  can override a code default.
