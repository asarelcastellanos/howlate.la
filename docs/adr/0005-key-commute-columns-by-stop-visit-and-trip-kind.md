---
status: accepted
date: 2026-11-26
---
# 0005. Key commute columns by stop visit and trip kind

Accepted by default, not reviewed by the owner.

## Context and problem statement

`route_file` keyed each cell by `(stop_sequence, stop_id)`. A timetable version that renumbers stop_sequence made one stop two columns, and the page decoder's `order.indexOf` keeps only the first, so the days under the second column dropped out (#229). On the 56 days ending 2026-11-24, line 33 direction 1 weekday from Venice / Figueroa (140726) to Venice / Redondo (15305) had 38 days in the arrival rows and 33 in the files. Both stops had two columns in the 7:54 pattern (start 28440). The ride time differed by 16 seconds, over the 10 second tolerance of C23.

Merging the columns exposed a second fault. Two trips of one day can share a scheduled start and call at different stops. On line 720 direction 1, trip `10720013670730-JUNE26` had Wilshire / Vermont (16769) and no Westwood / Wilshire (5208), and trip `10720013680730-JUNE26` had 5208. One column then held A from one bus and B from the other, which put 3 days in the files that the rows reject (30 against 27 days, a ride time off by 27 seconds).

## Considered options

* Key a cell by stop and visit, and give each kind of trip on a day its own column, with the page counting a day once
* Key a cell by stop and visit, and keep only the trip with the most measured rows for each day and start
* Key a cell by stop and visit and merge every trip of a day into one column
* Leave the keys and make the page read every column of a repeated stop

## Decision outcome

Chosen option: "Key a cell by stop and visit, and give each kind of trip on a day its own column, with the page counting a day once", because it is the only option where a ride time always comes from one bus and every day counts.

* A cell is keyed by stop and visit, the nth call at that stop within its trip by stop_sequence, so a renumbered stop is one column and a loop's repeat is still its own.
* Columns run in order of scheduled offset, then stop_sequence.
* Trips of one day and start that call at the same stops share a column and keep the earlier time at each stop. Trips that call at different stops get one column each, so `day_indexes` may list a day more than once.
* The page decoder (`dayTimes` in `web/src/lib/commute/ridetime.ts`) drops a column without both stops and counts a day once, at its earliest time at each stop. `rideTimes`, `candidate` and `arrivalSpread` use it. The file format keeps its shape, and a file with no repeated day index decodes as before.

Keeping only the largest trip lost 32 of 33 days on line 720 at one start, because the variant a commuter rides is often not the largest. Merging every trip kept the mix of two buses. Reading every column of a repeated stop needs a rule for which column to trust and still splits days.

### Consequences

* Good, because line 33 counts 38 days from the rows, the files and the decoder.
* Good, because the stop columns of a pattern fall from 154 to 84 on line 33, which shrinks the files. The largest gzipped file on the 56 days ending 2026-11-24 is 408,614 bytes, under the 450,000 byte limit.
* Bad, because the stop order now follows the scheduled offset, and two stops at the same offset are ordered by their lowest stop_sequence.
* Bad, because a decoder that reads one column per day index counts a repeated day twice.
