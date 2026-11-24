---
status: accepted
date: 2026-11-24
---
# 0002. Match rail runs by position when the id fails

Accepted by default, not reviewed by the owner.

## Context and problem statement

The grader joins each vehicle report to the timetable by the trip id the report carries. For rail that id is wrong on some days. #177 rebuilt each train's run from latitude and longitude on five days. On a normal day, lines 802 to 807 reported the trip the train ran in 91.6% to 100% of confident runs, and the reported startTime agreed with the reported trip's first departure in 100% of runs. On days when the timetable in force runs a line as split pieces and a later service runs it through (801 on 2026-11-13 to 11-15, 803 on 11-07), the feed labelled trains with ids from the later service, or with a nearby trip of the service in force. There the id named the run in 11% to 21% of confident runs. Position, route and direction held up, and trip id, startTime and vehicle id did not.

The grader dropped the later-start ids, which left 1,133 rail trips ungraded (#166). Grading them on their ids read as a median 30 minutes early (#166), so the choice is how to grade a train whose label is wrong.

## Considered options

* Trust the reported id always, as before
* Match every rail run by position and ignore the id
* Trust the id when it checks out, and match by position when it does not

## Decision outcome

Chosen option: "Trust the id when it checks out, and match by position when it does not", because it changes nothing on the days and lines where the id is right and grades the days where it is wrong.

A run is rebuilt from positions as `rail_runs.py` does, now in `railmatch.py`. Two routes can share track, and a run on it is explained equally by both station lists. The reported routeId of the run's records then breaks the tie, and position decides everything else. Each run is one of three.

* Trusted. The run's most common reported id is a trip of the timetable copy in force with a service running that day, and the most common reported startTime is within 120 seconds of that trip's first departure, and the run is not a misfit. A misfit is the rule `rail_misfit_pct` uses: another trip of the run's piece and direction fits within 60 seconds and the reported trip is 300 seconds or more worse. The run is graded as before. A run that passes the first two tests and is a misfit goes on to the next rule.
* Matched. Otherwise the run is fitted to the trips in force on its station list and direction. When the best trip's median miss is 120 seconds or less and the next trip is at least 120 seconds worse, the run is graded against that trip. Its rows carry `source` `matched`.
* Ungraded. Any other run, and any rail report outside every run, is not graded.

The daily report counts the three per line. `rail_misfit_pct` needs no new rule, because the grader now gives it the trip it graded, so it judges that trip. The matcher sits behind `railmatch.ENABLED`, which ships `False`. #178 set the bar for turning it on at 95% agreement with the reported id on every line with 30 or more trusted runs on a normal weekday. On 2026-11-13 and 11-20 it agreed in 91.6% to 100% of confident fits, and lines 801 (92.5% on 11-20), 804 (94.6%, 91.6%) and 805 (92.7%, 93.9%) fell under 95%. A second round added the route tie-break and the misfit test, and set the bar for turning it on at 95% on every line with 30 or more trusted runs on both 2026-11-18 and 11-19, with misfit ids set aside. 801 (84.2% and 88.5%), 804 (91.6% on 11-18) and 807 (92.5% on 11-19) fell short. So the grader reads rail as before until the owner turns it on. The 120 second limits come from #177, where the confident set kept runs within 120 seconds of a trip. A new `source` value adds no column, so `arrivals.VERSION` stays `v2`, as it did when #182 added `interpolated`.

The agreement of the matcher with the reported id on days when the id is good, and the regrade of the four problem days with the matcher on, are on #178.

### Consequences

* Good, because with the matcher on, a day like 2026-11-13 grades the 801 trains that ran, on the trip they ran, and the rail check stops failing on a fault the grader no longer has.
* Bad, because the matcher ships off, so the published rail numbers do not change and the later-start trips stay ungraded until the owner turns it on.
* Good, because a line with good ids grades as before except for the runs that do not check out.
* Bad, because a train a headway late fits the next trip as well as its own, so it is not confident and stays ungraded. The late trains of a split day are missing from the rail numbers, which makes the day look better than it was.
* Bad, because an id and a startTime that are stale together pass the first two trust tests. The misfit test catches those whose true trip fits within 60 seconds. Where the true trip fits in 61 to 120 seconds, the id stays trusted.
* Bad, because a rail report outside every run, such as a vehicle with no id, is no longer graded, so rail coverage can fall on a day that graded before.
* Bad, because grading reads every rail position of the day in Python, which adds 31 to 39 seconds a day with the matcher on (measured on #178). With the matcher off no matching work runs.
* Bad, because with the matcher off, `rail_misfit_pct` still judges the reported ids and fails on a split-service day such as 2026-11-13 (801 at 20.5% against 10%). The owner decided to report it and not fail the job, so while `railmatch.ENABLED` is `False` the check runs, prints and saves as before but does not fail the day, the exit code or the heartbeat. Turning the matcher on makes it binding again.
