# Review rules

These rules override the defaults in the `pr-review` skill.

## What failure looks like here

- A minute of collection is lost. The collector stops writing, writes a file
  that never uploads, or drops one feed without raising the alarm. This cannot
  be undone.
- A delay is wrong. A record lands on the wrong service day, joins the wrong
  scheduled stop, or uses the wrong timetable version, and the median still
  looks plausible.
- Coverage is overstated. A number built on a few sightings looks like one
  built on hundreds, or unobserved stops disappear from the count.
- A rerun damages other data. Rerunning one day changes another day, or leaves
  stale files that get counted twice.
- Something writes to or deletes from `gs://howlate-raw` outside the collector.

## Risk tiers

| Tier | Paths and changes | Review depth |
|---|---|---|
| High | Anything in `collector/`. `.github/workflows/`. Bucket lifecycle rules, permissions, and IAM. Anything that deletes or rewrites stored data. Parquet schema or layout changes. | Deep, and the owner reads the diff before merge |
| Medium | `pipeline/` logic, `aggregate` output, the data contract, how the site loads data | Standard |
| Low | Docs, copy, styles, templates | Quick |

An agent's approval never replaces the owner's on a high-risk change.

## Skip

- `.venv/`, `*.egg-info/`, and generated files.
- Formatting-only diffs produced by `ruff format`, unless the diff changes
  behavior.

## Claims in docs and comments

A sentence in docs or comments must not claim more than the code or the data
shows. v0.1.0 needed five fixes of this kind across two PRs: collection called
continuous despite a 16-hour gap, every scheduled stop implied to have an
observed arrival when about half do, a monthly cost stated as fixed when it
grows, and two alarms described as catching more than the code detects. Check
every number and every "all", "every", "always" and "never" against the code or
the buckets.

## Findings

- Every finding names a file and line and gives a concrete failure scenario:
  an input or state, and the wrong result it produces.
- Report at most three nits.
- A finding in code the change did not touch is tagged pre-existing.
