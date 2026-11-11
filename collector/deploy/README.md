# Deploying the collector

How the machine is put together. How the code works is documented in the code:
start at `src/howlate_collector/__init__.py`.

## The machine

| | |
|---|---|
| Instance | `howlate-collector`, `us-west1-b` |
| Type | `e2-micro`, 2 shared vCPU, 1 GB memory |
| Disk | 30 GB `pd-standard` |
| Bucket | `gs://howlate-raw`, `US-WEST1`, standard class |

The instance type, the disk size and the region are not arbitrary. One
`e2-micro` in `us-west1` with a 30 GB disk is exactly Google's always-free
allowance, so the compute costs nothing and only storage is billed.

Paths on the machine:

```
/opt/howlate/repo          the git checkout, whole repository
/opt/howlate/venv          the virtualenv, collector dependencies only
/var/lib/howlate/data      the spool, where files wait to be uploaded
/etc/howlate/env           the heartbeat URL, root-owned, outside the repo
```

The collector writes about 1 GB a day compressed, from roughly 15 GB of raw
text. With 26 GB free, that leaves around three weeks of spool room if Cloud
Storage becomes unreachable, which is the outage the compression is sized for.

## Before setup.sh will work

Two things have to exist first, and neither is created by the script.

**A service account on the instance** with write access to the bucket. This is
how both the uploader and the timetable job authenticate. There is no key file
anywhere on the machine.

**`/etc/howlate/env`**, holding one line:

```
HOWLATE_HEARTBEAT_URL=https://hc-ping.com/<uuid>
```

Owned by root, mode 0640. systemd reads it before dropping to the `howlate`
user, so the user itself never needs access. The recorder runs fine without this
file; it just goes unwatched.

## Deploying

```bash
gcloud compute ssh howlate-collector --zone=us-west1-b --command="
  sudo git -C /opt/howlate/repo fetch origin &&
  sudo git -C /opt/howlate/repo reset --hard origin/main &&
  sudo bash /opt/howlate/repo/collector/deploy/setup.sh
"
```

`setup.sh` is idempotent and is also what sets up a fresh VM. It restarts rather
than starts, so a redeploy actually picks up the new code, and SIGTERM gives the
recorder time to finish and compress the file it has open.

Continuous deployment is worth building when deploys are frequent. This one
changes a few times a year, so a command is cheaper than a pipeline.

## Checking it worked

```bash
sudo journalctl -u howlate-record -n 20 --no-pager
```

Healthy output looks like this, with both feeds named and a finished file every
five minutes:

```
  [LACMTA] connected
  [LACMTA_Rail] connected
  finished vehicle_positions-20260818T043014Z.jsonl.gz (LACMTA=61402, LACMTA_Rail=6284)
```

Those counts swing widely by time of day, but they never reach zero. Metro sends
around the clock: measured across the first 1,422 files, every one held records
from both feeds, and the quietest five minutes ever recorded still carried 13,396
bus and 135 rail messages. So a file every five minutes with **both** feeds named
is the whole health check. One name missing means half the network is going
unrecorded, and no file at all means nothing is being recorded.

Three more things worth a glance in the first hour:

```bash
ls /var/lib/howlate/data | wc -l    # near zero: the uploader is keeping up
df -h /                             # flat: nothing is piling up
gcloud storage ls "gs://howlate-raw/vehicle_positions/dt=$(date -u +%F)/"
```

## When something goes red

**`howlate-timetable` failed, exit 2.** The timetables saved correctly, but the
lines Metro publishes no longer match the ones being recorded. The log names
which. Refresh the list, commit, redeploy:

```bash
.venv/bin/python -m howlate_collector.routes
```

Do not just clear the failure. Until the list is refreshed, any new line is going
unrecorded, and that is the one thing this project cannot go back and fix.

**`howlate-timetable` failed, exit 1.** A download failed. It retries in six
hours and no data is at risk.

**The heartbeat reported a failure.** Something has stopped delivering. The log
says which of the two:

```
  nothing from either feed in 10 min, raising the alarm
  nothing from LACMTA_Rail in 3 files, raising the alarm
```

Both are usually Metro rather than this machine, and both clear on their own when
the feed comes back. The alarm repeats every ten minutes for as long as it lasts,
so a single one means it recovered.

**The heartbeat went quiet altogether.** The machine is gone, or the recorder is
not running. Nothing is being collected and nothing will alarm about it, because
the thing that would raise the alarm is the thing that stopped.

**`connected but silent for 5 min, reconnecting`.** Working as intended, no
action needed. Metro handed out a socket that was open but delivering nothing and
the recorder threw it away. Worth watching only if it repeats for hours, which
means Metro is consistently serving dead subscriptions.

**The spool directory is growing.** Uploads are failing. Collection continues and
nothing is lost yet; there are about three weeks of room. Check
`journalctl -u howlate-upload`.

## Cold storage

Raw vehicle positions move to Coldline after 30 days and to Archive after 365,
following `raw-lifecycle.json`. Timetables under `gtfs/` stay Standard, because
every regrade reads them. The rule never deletes anything. `tests/test_lifecycle.py`
checks those properties of the file; CI runs it on every PR and every push to
main, and the command below runs it on the exact file being applied.

The rule is applied by hand, by the owner, and only once a backfill has graded
every day it needs: a backfill run after the rule pays a retrieval fee on every
day older than 30 days.

```
.venv/bin/python collector/tests/test_lifecycle.py && \
  gcloud storage buckets update gs://howlate-raw --lifecycle-file=collector/deploy/raw-lifecycle.json
gcloud storage buckets describe gs://howlate-raw --format='yaml(lifecycle_config)'
```

Google applies it within about a day. Reading raw positions older than 30 days
then costs a retrieval fee of $0.02/GB from Coldline and $0.05/GB from Archive.
A day's partition is about 1.2 GB. Grading one day reads three partitions, the
day and the UTC days either side, so regrading a single old day reads about
3.6 GB; a backfill over a range shares them and averages about 1.2 GB a day.
The daily job reads files up to about ten days old, so it pays none.

## Security

The instance has its own identity with permission to write to one bucket and
nothing else. Credentials are issued automatically and expire on their own, so
there is no key file on the machine, nothing to rotate, and nothing to leak if
the instance were compromised.

The collector runs as `howlate`, a system user with no login shell, which cannot
log in or reach anything outside its own directory.

The one genuine secret is the heartbeat URL, which lives in a root-owned file
outside the repository. Anyone holding it can silence the alarm, which is the
only harm it can do.
