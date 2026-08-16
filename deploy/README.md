# Deploying

Two long-running processes and one timer on a single `e2-micro` in `us-west1-b`, supervised by systemd. Data lands in `gs://howlate-raw`.

## Why a VM and not Cloud Run

The upstream is a push websocket (`wss://api.metro.net/ws/LACMTA/vehicle_positions/...`), not a pollable endpoint. Holding a socket open for weeks is not request-shaped, so Cloud Run would mean `min-instances=1` with CPU always allocated: an always-on container with extra abstraction and no scaling benefit. The timetable job *is* Cloud Run shaped, but standing up a second deploy path (image build, Artifact Registry, Cloud Scheduler, another service account) for a 40-line script that runs four times a day is not worth it while a VM is already running.

## Topology

| Unit | Type | Purpose |
|---|---|---|
| `howlate-record.service` | `simple`, `Restart=always` | Holds the websocket, writes `data/*.jsonl` |
| `howlate-upload.service` | `simple`, `Restart=always` | gzip + upload finished files, unlink on success |
| `howlate-timetable.timer` | `OnCalendar=*-*-* 00,06,12,18:10:00 UTC` | Triggers the oneshot GTFS snapshot |

`WorkingDirectory=/var/lib/howlate`, all three run as the system user `howlate` (`nologin`, no shell). Code lives at `/opt/howlate/repo`, venv at `/opt/howlate/venv`.

## Process coordination

The recorder and uploader share no state and never communicate. The entire protocol is a filename:

```
vehicle_positions-20260816T025034Z.jsonl.partial   open, being written
vehicle_positions-20260816T025034Z.jsonl           closed, safe to upload
```

The uploader globs `vehicle_positions-*.jsonl`, which excludes `.partial` by construction. The transition is a `rename(2)` within one directory, so it is atomic: a file is never observable in a half-renamed state, and no locking is required.

`recover_orphans()` runs at recorder startup and promotes any leftover `.partial` to `.jsonl`. Without it, a `SIGKILL` or power loss would strand the final minutes of collection on disk permanently, since the uploader would never match it. Safe because systemd guarantees a single recorder instance.

## Shutdown semantics

`Restart=always` handles crashes, but the interesting path is the clean stop, because that is what runs on every deploy.

- `SIGTERM` and `SIGINT` are registered via `loop.add_signal_handler` and set an `asyncio.Event`. Python does **not** convert `SIGTERM` into `KeyboardInterrupt`, and `KeyboardInterrupt` does not reliably break out of `asyncio.wait_for`, so relying on exceptions here silently fails on a server.
- `websockets.connect(..., close_timeout=1)`. The library default is 10s, spent waiting for a close handshake Metro never completes. Left at the default, shutdown exceeds `TimeoutStopSec` on slower paths and systemd escalates to `SIGKILL`, which is precisely the case that strands a `.partial`.
- The read loop uses `asyncio.wait_for(socket.recv(), timeout=1)`. That 1s bound is both the rotation-check interval and the stop-signal latency. Cancelling `recv()` this way is safe: measured 697 vs 698 messages against an uninterrupted `async for` over 40s.

Measured stop latency after these fixes: **0.6s on SIGTERM, 1.6s on SIGINT**, file finished in both cases.

## Rotation

Rotation is driven by a clock check inside the read loop, not by message arrival. Metro's feed is bursty: roughly 40 messages within 10ms, then 1 to 4 seconds of silence (754 of 772 inter-message gaps under 10ms; 18 gaps of 1 to 4s). Tying rotation to arrivals inherits that raggedness, and during the ~2am to 5am lull it would hold a file open for hours.

The same check runs inside the reconnect backoff loop, so an extended outage still rotates and uploads on schedule rather than pinning collected data on local disk.

Rotation performs no `await` between `close()` and the next `_open()`, so it cannot be preempted mid-swap. Messages arriving during the few milliseconds it takes are buffered by the socket and drained on the next iteration.

## Reconnection

`websockets.connect` sits inside a retry loop. On any non-`CancelledError` exception the recorder logs, waits, and reconnects with exponential backoff capped at 60s, resetting to 1s on a successful connect.

The open file is deliberately **not** closed on disconnect. Closing on every drop turns a flapping link into file spam: an early version produced 16 files of 3 records each across 16 reconnects, versus 1 file of 48 records after the fix.

## Deploy

Push to `main`, then pull on the VM and re-run setup:

```bash
gcloud compute ssh howlate-collector --zone=us-west1-b --command="
  sudo git -C /opt/howlate/repo fetch origin &&
  sudo git -C /opt/howlate/repo reset --hard origin/main &&
  sudo bash /opt/howlate/repo/deploy/setup.sh
"
```

`setup.sh` is idempotent. Two things it gets right that are easy to get wrong:

**`systemctl restart`, not `enable --now`.** `--now` starts a unit only if it is inactive, so on a redeploy the running process keeps its old code and old environment while the deploy reports success. This cost us a debugging cycle: services showed `active`, the deploy printed `Done`, and `EnvironmentFile` changes had not been picked up.

**Never bootstrap from `raw.githubusercontent.com`.** It is CDN-cached for several minutes, so a redeploy shortly after a push silently installs the previous revision. Pull into the VM's own clone instead, where `git log -1` is ground truth for what is deployed.

Verify what is actually running:

```bash
gcloud compute ssh howlate-collector --zone=us-west1-b --command="
  git -C /opt/howlate/repo log -1 --oneline
  systemctl show howlate-record -p ActiveEnterTimestamp --value
  sudo cat /proc/\$(systemctl show howlate-record -p MainPID --value)/environ | tr '\0' '\n' | grep HOWLATE
"
```

Checking the process environment rather than `systemctl is-active` is the check that would have caught the `enable --now` bug.

## Provisioning from scratch

```bash
gcloud storage buckets create gs://howlate-raw \
  --location=us-west1 --uniform-bucket-level-access --public-access-prevention

gcloud iam service-accounts create howlate-collector
gcloud storage buckets add-iam-policy-binding gs://howlate-raw \
  --member="serviceAccount:howlate-collector@howlate-la.iam.gserviceaccount.com" \
  --role=roles/storage.objectAdmin

gcloud compute instances create howlate-collector \
  --zone=us-west1-b --machine-type=e2-micro \
  --image-family=debian-13 --image-project=debian-cloud \
  --boot-disk-size=30GB --boot-disk-type=pd-standard \
  --service-account=howlate-collector@howlate-la.iam.gserviceaccount.com \
  --scopes=https://www.googleapis.com/auth/cloud-platform

# then on the instance
sudo apt-get update && sudo apt-get install -y git
sudo git clone https://github.com/asarelcastellanos/howlate.la.git /opt/howlate/repo
sudo bash /opt/howlate/repo/deploy/setup.sh
```

Always-free eligibility is narrow and all four conditions must hold: `e2-micro`, one of `us-west1`/`us-central1`/`us-east1`, `pd-standard` (not balanced or SSD), and 30GB or less. `us-west2` is Los Angeles and is the tempting wrong answer.

## Credentials

The instance runs as the `howlate-collector` service account, scoped to `roles/storage.objectAdmin` on the one bucket. ADC resolves through the GCE metadata server, so `google.cloud.storage.Client()` authenticates with no configuration and no key material on disk. Nothing to rotate, nothing to leak.

Locally, the same code path requires `gcloud auth application-default login`, which is a separate credential from `gcloud auth login`. Only the former is read by client libraries; having only the latter produces `DefaultCredentialsError` while `gcloud` commands work fine.

## Configuration

`/etc/howlate/env`, root-owned, mode `0640`:

```
HOWLATE_HEARTBEAT_URL=https://hc-ping.com/<uuid>
```

Referenced as `EnvironmentFile=-/etc/howlate/env`. The leading `-` makes it optional, so a host without monitoring configured still starts.

The recorder pings this once per finished file via `asyncio.to_thread(requests.get, ...)` with all exceptions swallowed. A monitoring failure must never affect collection. Treat the URL as a credential: it is a write endpoint, and anyone holding it can mask a real outage with fake pings. The badge UUID in the top-level README is a distinct read-only identifier and is safe to publish.

## Storage layout

```
gs://howlate-raw/
├── vehicle_positions/dt=YYYY-MM-DD/hh=HH/vehicle_positions-<ts>.jsonl.gz
└── gtfs/gtfs_bus-YYYY-MM-DD-<etag8>.zip
```

`dt=`/`hh=` is Hive-style partitioning, so a BigQuery external table over this prefix can prune by day and hour instead of scanning the archive. Partition values come from the recorder's filename, which is already UTC, so the uploader derives them without opening the file.

GTFS snapshots are keyed by source ETag and never overwritten. Metro revises schedules, and the same `trip_id` can be assigned a different scheduled time, so an observation must be joined against the snapshot in effect on the day it was recorded. The full ETag is stored in object metadata; the filename carries a truncated form for readability only, and the comparison uses the metadata.

Records are stored unmodified. Metro's payload is spliced into the envelope as raw text rather than decoded and re-encoded, so byte-level fidelity is preserved:

```json
{"received_at":"2026-08-16T02:31:03.891778Z","payload":{ ...verbatim... }}
```

No deduplication on write, despite roughly 3x rebroadcast in the feed. It is a lossy irreversible transform that saves cents. Deduplicate at read time on `(vehicle id, timestamp)`.

## Capacity

Observed: 15 to 30 messages/sec depending on time of day, roughly 5,000 records per 5-minute file at peak, compressing 11x to 24x. Around 2 GB/month in the bucket.

Local disk only accumulates during an upload outage. 26GB free at roughly 600MB/day of uncompressed spool gives well over a month of runway before disk pressure. Memory sits at ~430MB of 964MB, which is the tightest resource on `e2-micro`.

## Failure modes

| Failure | Handling |
|---|---|
| Process crash | `Restart=always`, `RestartSec=5`; orphaned `.partial` recovered at startup |
| Websocket drop | In-process reconnect, exponential backoff to 60s, file kept open |
| GCS unavailable | Uploader retries next sweep; recorder unaffected; files persist locally |
| Instance reboot | Both units `WantedBy=multi-user.target`; timer is `Persistent=true` so a missed run fires on boot |
| Instance gone, or feed silent while connected | Not detectable in-process. Heartbeat gap triggers an external alert. |

That last row is why the heartbeat exists. Everything above it is recoverable locally; nothing in-process can observe its own absence.

## Observability

```bash
# live log
gcloud compute ssh howlate-collector --zone=us-west1-b \
  --command="sudo journalctl -u howlate-record -f"

# is data still landing
gcloud storage ls "gs://howlate-raw/vehicle_positions/dt=$(date -u +%F)/"

# next timetable run
gcloud compute ssh howlate-collector --zone=us-west1-b \
  --command="systemctl list-timers howlate-timetable"
```

The badge in the top-level README is the cheapest liveness signal available.
