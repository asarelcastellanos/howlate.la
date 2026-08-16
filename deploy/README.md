# Deploying

The collector runs on a single `e2-micro` VM in `us-west1`, under systemd.

## Redeploying after a code change

Push to `main`, then on the VM pull and re-run setup:

```bash
gcloud compute ssh howlate-collector --zone=us-west1-b --command="
  sudo git -C /opt/howlate/repo fetch origin &&
  sudo git -C /opt/howlate/repo reset --hard origin/main &&
  sudo bash /opt/howlate/repo/deploy/setup.sh
"
```

**Pushing to GitHub does not update the VM.** Nothing connects them: no webhook,
no auto-deploy. The VM changes only when the commands above run on it.

Do not bootstrap from `raw.githubusercontent.com`. That URL is served through a
CDN which caches for several minutes, so a redeploy run soon after a push will
silently install the previous version. Pulling in the VM's own clone avoids that
entirely, and `git log` there tells you exactly which commit is deployed.

## First-time setup on a fresh VM

`setup.sh` needs the repo present, so the very first run does have to fetch the
script from somewhere. Clone first, then run it locally:

```bash
sudo apt-get update && sudo apt-get install -y git
sudo git clone https://github.com/asarelcastellanos/howlate.la.git /opt/howlate/repo
sudo bash /opt/howlate/repo/deploy/setup.sh
```

## What runs

| Unit | What it does |
|---|---|
| `howlate-record.service` | Listens to Metro's live feed, writes files. Restarts on failure. |
| `howlate-upload.service` | Ships finished files to `gs://howlate-raw`, deletes on success. |
| `howlate-timetable.timer` | Runs the schedule check every 6 hours. |

## Configuration

`/etc/howlate/env` holds settings that should not be in git:

```
HOWLATE_HEARTBEAT_URL=https://hc-ping.com/...
```

Root-owned and mode `0640`. The heartbeat URL is effectively a secret: anyone
holding it can send fake pings and hide a real outage.

The unit file references it with `EnvironmentFile=-/etc/howlate/env`. The leading
dash means the service still starts if the file is absent, so a machine without
monitoring configured runs normally, just unwatched.

## Checking on it

```bash
# live log
gcloud compute ssh howlate-collector --zone=us-west1-b \
  --command="sudo journalctl -u howlate-record -f"

# is data still landing?
gcloud storage ls "gs://howlate-raw/vehicle_positions/dt=$(date -u +%F)/"

# when does the timetable check next run?
gcloud compute ssh howlate-collector --zone=us-west1-b \
  --command="systemctl list-timers howlate-timetable"
```

## Authentication

The VM has a service account attached (`howlate-collector@...`) with
`roles/storage.objectAdmin` on the bucket and nothing else. Google supplies
short-lived credentials through the metadata server, and the Python client picks
them up automatically. There is no key file anywhere on the machine.
