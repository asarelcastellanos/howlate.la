# HowLate

**howlate.la**

Is my bus usually late? And when is it worst? Nobody was writing that down, so this does.

## Goal

LA Metro publishes where every vehicle is and where it was supposed to be. Every bus and train reports its own position every six or seven seconds, all day, every day, in public.

Trip planners like Transit show you the next arrival, and the number disappears the moment the bus pulls up. It was true for 90 seconds and then it's gone. So a rider who wants to know whether the 720 westbound is reliably late at 8am on a Tuesday has nowhere to look.

HowLate.LA writes it down. Then publishes the answer.

## Status

Collection started on 18 August 2026. It has missed one stretch since, 16 hours
on 21 August, when Metro served a socket that stayed open and sent nothing. It records
everything Metro runs to a schedule: all 114 bus routes and all six rail lines.

The pipeline grades each day against the timetable every morning without anyone
running it. The site is built and live at [howlate.la](https://howlate.la). You
can search for a bus or train line and see how late it usually runs, by day and
hour, and see which lines are the most and least reliable.

What is planned next is in the [release plan](docs/release-plan.md), and
progress is tracked in the
[milestones](https://github.com/asarelcastellanos/howlate.la/milestones).

## What it collects

Two things.

**Where the buses and trains actually are.** Metro broadcasts the position of
every vehicle it runs, updated every few seconds. HowLate listens to all of it
and writes down every update.

**Where they were supposed to be.** Metro also publishes its timetables: every
scheduled stop, of every trip, on every line. Those get revised as service
changes, so a fresh copy is kept each time they do. Measuring August's buses
against September's timetable would give answers that are wrong.

Those two together are the whole idea. If the timetable says a bus should reach
your stop at 8:14 and the feed shows it pulling in at 8:23, that bus was nine
minutes late.

Both feeds are public. Metro publishes them for developers.

## How it works

A small always-on machine holds two connections open, one to the bus feed and
one to rail, and writes down every update it hears. Every five minutes it closes
the file, compresses it, ships it to cloud storage, and starts a new one.

Separately, a few times a day, it checks whether Metro has republished its
timetables and keeps a copy if so. That check is also how it notices Metro
adding or dropping a line, which happens more often than you would think.

Grading happens somewhere else, later. The pipeline reads a day of positions,
finds the timetable that was in force that day, and writes one row for every
stop every trip was scheduled to make: when it should have arrived and, where a
vehicle was seen there (about half the time), when it did and the difference.


## By the numbers

|  |  |
|--:|:--|
| **120** | lines watched: every bus route and rail line Metro runs to a schedule |
| **6 seconds** | how often each vehicle reports where it is |
| **~400** | updates arriving every second at the busy hours |
| **~25 million** | records written down a day |
| **~1.2 GB** | added to the archive a day, squeezed from 15 GB of raw text |
| **about $1.50** | a month to run, projected from the first 24 days of the November 2026 billing report (read on 2026-11-24), almost all of it archive storage. It grows with the archive. |

The running cost for November 1 to 24 was about $1.20. Standard storage was $0.81 and write operations were $0.23. The collector VM cost $4.65 before the free-tier credit, which brings it to about zero. The month had not closed when I read the report.

The same 24 days also carried $23.96 in one-time charges.

- $19.11 for downloading 259 GiB of the raw archive to a laptop
- $3.49 for retrieving 175 GiB from Coldline
- $0.85 for Coldline read and write operations
- $0.51 for the Spot VM that ran two backfills

The pipeline now refuses raw downloads outside Google Cloud, so the download charge should not repeat.


## What's in this repo

```
collector/    Listens to Metro and writes everything down.
              The only part that runs on the always-on machine.

pipeline/     Turns the raw archive into how late each vehicle was,
              and builds the files the site reads. Runs every morning.

web/          The public site. Reads what the pipeline produced.
              Live at howlate.la.

docs/         The release plan.
```

## Data

Vehicle positions and timetables are published by LA Metro for developers.
HowLate is not affiliated with LA Metro.

