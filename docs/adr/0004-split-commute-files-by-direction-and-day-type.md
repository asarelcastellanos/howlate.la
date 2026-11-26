---
status: accepted
date: 2026-11-24
---
# 0004. Split commute files by direction and day type

Supersedes [ADR-0003](0003-ship-commute-data-as-route-files-built-daily.md).

## Context and problem statement

ADR-0003 chose one commute file per bus route and estimated 130 KB gzipped for the busiest one. The sizing script `pipeline/scripts/commute_sizing.py` then ran on the backfill VM over the 56 days ending 2026-11-23 (#34). Exact ride time from stop A to stop B needs each day's time at each stop on the same trip. In that layout one file per route reached 2,274,796 bytes gzipped for line 4 and 609,853 bytes for the median line. Even the per-stop spread alone reached 355,933 bytes for line 4.

## Considered options

* One file per route, direction and day type, with each day's time per stop rounded to 10 seconds and coded as the change from the stop before, and a limit of 450 KB per file
* The same split, with weekday files over 300 KB split again into morning, midday and evening
* The same split with whole seconds, where 42 files pass 300 KB and the largest is 606 KB
* One file per route with the per-stop spread only, so ride time is no longer from the same trip
* One file per route as in ADR-0003, up to 2.3 MB

## Decision outcome

Chosen option: "One file per route, direction and day type, with each day's time per stop rounded to 10 seconds and coded as the change from the stop before, and a limit of 450 KB per file", because ride time stays from the same trip and a visit loads one file.

The second sizing run measured all 632 files. With this encoding the median file is 27,557 bytes at gzip level 6, the 95th percentile is 214,672, and the largest is 411,809. Six files pass 300 KB. They are the weekday files of lines 4, 2 and 33 in both directions, at 317,807 to 411,809 bytes. The build ran in batches with a peak of 1.14 GB of memory and took 502 seconds for six encodings, so one encoding fits the daily job. The stop list is 192,639 bytes at gzip level 6. ADR-0003's other choices stay. The daily job builds the files, and the day type comes from the stored GTFS calendar.

### Consequences

* Good, because ride time from A to B comes from the same trip on the same day, as C7 requires.
* Good, because a visit loads the stop list and one file, about 220 KB for the median file.
* Bad, because each stop time is off by up to 5 seconds, so a ride time is off by up to 10 seconds. The page shows whole minutes.
* Bad, because a visit to a weekday commute on line 4 loads about 600 KB with the stop list, which is slow on a weak phone connection.
* Bad, because a route grows past 450 KB if its weekday service grows by about a tenth. The build must fail the day when a file passes the limit, so the growth shows up.
