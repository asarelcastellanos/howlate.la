# HowLate

**howlate.la**

A personal project that answers one question: *is my bus usually late, and when is it worst?*

## Goal

LA Metro publishes, continuously, where every vehicle is and where it should be. Nobody keeps the difference (at least publicly).

Trip planners and other apps show the next arrival and discard it the moment the bus shows up. So a rider who wants to know whether the 720 westbound is reliably late at 8am on a Tuesday has nowhere to look, and it's not because the question is hard, but because nobody writes down the answer.

HowLate writes it down. Every minute. Then it publishes the answer.

## Status

**Phase 1: collection.** This repo currently does one thing: record what Metro's buses actually do, and archive Metro's published schedule alongside it.

This project currently tracks four routes: **20** and **720** on Wilshire Bl, **204** and **754** on Vermont Av. Each corridor gets a local and a rapid on the same street, which builds a controlled comparison into the data: same road, same traffic, same day, one bus stopping everywhere and one skipping most of them.

Both corridors are among the busiest Metro runs. By scheduled service the 720 has more trips than any other bus route in Metro's current feed, and Metro's own Vermont Transit Corridor study puts Vermont above 45,000 daily boardings.

## What it collects

Two things.

**Where the buses actually are.** Metro broadcasts the live position of every bus, updated every few seconds. HowLate listens for the four tracked routes and writes down every update.

**Where the buses were supposed to be.** Metro also publishes its timetable: every scheduled stop, for every trip, on every route. Metro revises that timetable as service changes, so HowLate saves a new copy each time it does.

Those two together are the whole idea. If the timetable says a bus should reach your stop at 8:14 and the live feed shows it pulling in at 8:23, that bus was nine minutes late.

Both feeds are public, published by Metro for developers.

## How it works

A small always-on machine sits and listens to Metro's live feed. Every update it hears gets written to a file. Every five minutes it closes that file, compresses it, and uploads it to cloud storage, then starts a new one.

Separately, once a day, it checks whether Metro has published a new timetable and saves a copy if so.

That's the whole system. It costs a few dollars a month to run, and the archive grows by roughly two gigabytes a month.

## What's next

Collecting is the slow part. A month of observations is roughly the point where patterns separate from noise, and there is no way to speed that up.

Once there's enough, the next step is matching each recorded arrival against the time it was scheduled for, which turns the raw archive into a plain list of how late each bus was. After that comes the part that answers the original question: grouping those delays by route, direction, stop, and time of day, and publishing the result.
