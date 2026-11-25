---
status: superseded by [ADR-0004](0004-split-commute-files-by-direction-and-day-type.md)
date: 2026-11-24
---
# 0003. Ship commute data as route files built daily

## Context and problem statement

The v0.6.0 commute tool answers "which bus, how long, how late" for a trip between two stops on one bus route. The site is static files on Cloudflare Pages with data on R2, and it has no server. The answer needs, for each departure pattern and stop, the spread of actual times over the last 8 weeks, counted by the timetable Metro ran each day. Graded arrivals do not store which service ran. The scout estimated about 60 KB gzipped per route, 130 KB for the busiest, and about 200 KB gzipped for a list of the 11,880 bus stops.

## Considered options

* One file per bus route and one stop list, built by the daily job from the timetable calendar
* One file per stop, built by the daily job
* A new arrivals column for the service day type, which makes arrivals v3

## Decision outcome

Chosen option: "One file per bus route and one stop list, built by the daily job from the timetable calendar", because a visit loads the stop list and one route file, about 260 KB, and the build needs no change to graded data and no regrade.

The daily Cloud Run job builds the files beside the existing line files and ships them through the same run folder and R2 copy. It reads arrivals it already fetches, in the same region, so the build adds no egress. It finds the day type of each date from the stored GTFS calendar.

### Consequences

* Good, because the commute page needs no server, and the files follow the run folder and pointer the site already uses.
* Good, because graded arrivals stay v2, so no day is regraded.
* Bad, because the site's run grows from about 3.8 MB to about 10 to 11 MB gzipped, and every daily run uploads all of it to R2.
* Bad, because a date whose stored GTFS has no calendar entry gets no day type, so its arrivals drop out of the commute answers.
* Bad, because a stop list of about 200 KB loads before a rider can search, which is slow on a weak phone connection.
