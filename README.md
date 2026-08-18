# HowLate

**howlate.la**

Is my bus usually late? And when is it worst? Nobody was writing that down, so this does.

## Goal

LA Metro publishes where every vehicle is and where it was supposed to be. Every bus and train reports its own position every six or seven seconds, all day, every day, in public.

Trip planners, like Tranist, shows you the next arrival and then it disspears the moment the bus pulls up. The number was true for 90 seconds and then its gone. So a rider who wants to know whether the 720 westbound is reliably late at 8am on a Tuesday has nowhere to look.

HowLate.LA writes it down. Then publishes the answer.

## Status

**Phase 1: collection.** This repo currently does one thing. It writes down what
Metro's buses and trains actually do, and keeps a copy of the timetable they
will be judged against.

It records everything Metro runs to a schedule: all 114 bus routes and all six
rail lines.

Collection started on 18 August 2026. Nothing is published yet.



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

That is the whole system. It costs under a dollar a month to run.


## By the numbers

|  |  |
|--:|:--|
| **120** | lines watched: every bus route and rail line Metro runs to a schedule |
| **6 seconds** | how often each vehicle reports where it is |
| **~400** | updates arriving every second at the busy hours |
| **~25 million** | records written down a day |
| **~1 GB** | added to the archive a day, squeezed from 15 GB of raw text |
| **under $1** | to run the whole thing for a month |


## What's in this repo

```
collector/    Listens to Metro and writes everything down.
              The only part that runs on the always-on machine.

pipeline/     Turns the raw archive into how late each vehicle was.
              Runs once a day, somewhere else. Not written yet.

web/          The public site. Reads what the pipeline produced.
              Not written yet.
```

## Data

Vehicle positions and timetables are published by LA Metro for developers.
HowLate is not affiliated with LA Metro.

