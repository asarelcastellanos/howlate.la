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
