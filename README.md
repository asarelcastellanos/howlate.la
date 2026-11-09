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

The pipeline that grades each day against the timetable is built and checked
against two full days. The site is not built yet. Nothing is published.

The road from here to howlate.la is in the [release plan](docs/release-plan.md),
and progress is tracked in the
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
| **~1 GB** | added to the archive a day, squeezed from 15 GB of raw text |
| **about $2** | a month to run as of November 2026, almost all of it archive storage. It grows about 75 cents a month until old files move to cold storage in 0.3.0 |


## What's in this repo

```
collector/    Listens to Metro and writes everything down.
              The only part that runs on the always-on machine.

pipeline/     Turns the raw archive into how late each vehicle was,
              and builds the files the site reads. Runs by hand for now.

web/          The public site. Reads what the pipeline produced.
              Not built yet.

docs/         The release plan.
```

## Data

Vehicle positions and timetables are published by LA Metro for developers.
HowLate is not affiliated with LA Metro.

