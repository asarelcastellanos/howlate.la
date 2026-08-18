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

Those counts swing widely by time of day and drop to nothing overnight. What
matters is that **both** feeds appear. One name missing means half the network is
going unrecorded.

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

**The heartbeat went quiet, or reported a failure.** Either the machine is gone,
or one feed has delivered nothing for fifteen minutes while the other kept going.
`journalctl -u howlate-record` will say which.

**The spool directory is growing.** Uploads are failing. Collection continues and
nothing is lost yet; there are about three weeks of room. Check
`journalctl -u howlate-upload`.

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
