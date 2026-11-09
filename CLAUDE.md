# HowLate

Records where LA Metro's buses and trains actually are, grades every scheduled
stop against the timetable, and will publish the result at howlate.la.

## Layout

```
collector/   Runs on the VM. Holds Metro's two live feeds open and writes
             everything to gs://howlate-raw. The only part where a failure
             loses data for good.
pipeline/    Runs elsewhere. Reads the raw archive, writes graded arrivals and
             the site's JSON to gs://howlate-derived.
web/         The public site. Not built yet.
docs/        The release plan.
```

Each package installs on its own. Never add a pipeline or site dependency to
`collector/pyproject.toml`, because that puts it on the VM.

## Commands

```bash
python3 -m venv .venv
.venv/bin/pip install -e collector -e "pipeline[test]" ruff
.venv/bin/python collector/tests/test_record.py   # collector tests
.venv/bin/python -m pytest pipeline/tests         # pipeline tests
.venv/bin/ruff check .                            # lint
.venv/bin/ruff format --check .                   # formatting
```

## Rules that protect the data

- The raw archive is append-only. Nothing outside `collector/` writes to
  `gs://howlate-raw`, and nothing anywhere deletes from it.
- Everything in `gs://howlate-derived` can be rebuilt from the raw archive, so
  it is safe to overwrite. A rerun of one day must replace only that day.
- Every scheduled time goes through `America/Los_Angeles` and the service day,
  never the machine's clock or the UTC day.
- Comments explain why, with the measurement that justified the choice. Keep
  that style when editing.

## How work ships

- Versions and their tests are in `docs/release-plan.md`. Each version is a
  GitHub milestone, and each issue in it is one PR.
- Feature branches are named `v0.X/short-name` and merge into
  `release/vX.Y.Z`. The release branch merges into `main` only with the
  owner's approval.
- Every PR follows the `ship-a-change` process. Review rules are in
  `REVIEW.md`.
- Commit messages and PR descriptions follow the `git-messages` skill, with no
  AI attribution.
