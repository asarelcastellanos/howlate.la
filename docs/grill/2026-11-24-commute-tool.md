# Grill: v0.6.0 commute tool

2026-11-24, in the main session with the question tool, after v0.5.2 shipped.

## Scope

| Question | Answer |
|---|---|
| What is v0.6.0? | The commute tool in `docs/release-plan.md`, issues #34 to #37, updated with what v0.5.2 taught. |
| Size | A version. Full grill, then a spec. |

## Round 1

| # | Question | Answer |
|---|---|---|
| Q1 | Rail trip ids are wrong on split-service days while the matcher is off. Which lines does the commute tool cover? | Bus only. The tool says rail is not covered yet. |
| Q2 | Do ride time and the "9 times in 10" answer use estimated stop times? | Measured only. |
| Q3 | Which days is an answer built from? | Last 8 weeks. |
| Q4 | Where does the commute screen live? | A new `/commute` page, linked from the home page and each line page. |

## Round 2

| # | Question | Answer |
|---|---|---|
| Q5 | Below how many observed days does a stop say "not enough data"? | 8 days. The page says how many days an answer rests on. |
| Q6 | How do holidays count in the 8-week window? | By the timetable Metro ran that day. |
| Q7 | How is "nearest stop" handled? | In the browser only. The location never leaves the phone, and a denied prompt falls back to search. |
| Q8 | Is the "9 times in 10" level fixed or adjustable? | Fixed at 9 in 10. |

## Round 3

A scout measured the current site before this round. The site is static files on Cloudflare Pages, with data on R2. The 115 line files are 21.0 MB raw and 3.8 MB gzipped. A distinct bus stop list of 11,880 stops is about 200 KB gzipped. Graded arrivals carry route, direction, trip, stop sequence and scheduled time, but not the service that ran.

| # | Question | Answer |
|---|---|---|
| Q9 | How does the daily job ship commute data? | One file per bus route and one stop list. [ADR-0003](../adr/0003-ship-commute-data-as-route-files-built-daily.md) |
| Q10 | How does the build find the timetable that ran on a date? | It looks the date up in Metro's stored GTFS calendar. No change to graded arrivals and no regrade. [ADR-0003](../adr/0003-ship-commute-data-as-route-files-built-daily.md) |

## Confirmation

The owner confirmed the summary on 2026-11-24 with "Yes, write the spec".

## Options offered

The options each question offered, with the chosen one first.

| # | Options |
|---|---|
| Q1 | Bus only. Bus and rail, rail flagged. Bus and rail, no flag. |
| Q2 | Measured only. Include estimates. |
| Q3 | Last 8 weeks. Every day collected. Current timetable only. |
| Q4 | New /commute page. On the home page. Inside each line page. |
| Q5 | 8 days. 15 days. 5 days. |
| Q6 | By timetable run. Leave holidays out. By calendar day. |
| Q7 | In the browser only. Drop nearest stop. |
| Q8 | Fixed at 9 in 10. Let the rider pick 3 in 4, 9 in 10 or 19 in 20. |
| Q9 | One file per route and a stop list. One file per stop. |
| Q10 | Look it up from GTFS. Add it to graded arrivals as a new column, which makes arrivals v3. |
