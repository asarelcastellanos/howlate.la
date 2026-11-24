---
status: accepted
date: 2026-11-24
---
# 0001. Refuse raw downloads outside Google Cloud

## Context and problem statement

`arrivals` and `backfill` download raw files from `gs://howlate-raw` into a local cache. Inside `us-west1` that read is free. From a laptop, Cloud Storage charges $0.12 per GiB after the first 100 GiB each month, and files older than 30 days also pay $0.02 per GB for Coldline retrieval. Between 2026-11-16 and 2026-11-18, laptop runs downloaded 259 GiB and cost $22.60, in a project that otherwise costs about $2 a month. Each run was small, and each started with an empty cache.

## Considered options

* Refuse every raw download outside Google Cloud, with an `--allow-egress` flag for a person
* Refuse every raw download outside Google Cloud, with no override
* Refuse only downloads above one service day
* Warn and continue

## Decision outcome

Chosen option: "Refuse every raw download outside Google Cloud, with an `--allow-egress` flag for a person", because the November cost came from many one-day runs that a size limit would have passed, and the owner still needs a way to force a download without a code change. `CLAUDE.md` forbids agents from passing the flag. The guard covers `gs://howlate-raw` only, because a full download of `gs://howlate-derived` is about 0.7 GB.

### Consequences

* Good, because a paid download now needs a deliberate flag and the command prints the cost first.
* Good, because the daily Cloud Run job and the backfill VM run unchanged.
* Bad, because grading a real day on a laptop now needs the backfill VM or raw files already on disk, which slows local debugging.
* Bad, because the guard depends on the metadata server to tell where it runs, and a wrong answer inside Cloud Run would fail the daily job.
* Bad, because the flag relies on a written rule to keep agents from passing it.
