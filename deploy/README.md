## Architecture

```
Metro's live feed  ──websocket──▶  recorder ──▶ local disk ──▶ uploader ──▶ Cloud Storage
                                                                                  ▲
                          Metro's published timetable ──every 6h──────────────────┘
```

One `e2-micro` instance in `us-west1`, running three things under systemd:

| | What it does | Lifetime |
|---|---|---|
| **recorder** | Holds a websocket to Metro open, writes every update to disk | continuous |
| **uploader** | Compresses finished files, ships them to Cloud Storage | continuous |
| **timetable** | Saves Metro's schedule when it changes | every 6 hours |

Storage is one bucket.

```
gs://howlate-raw/
├── vehicle_positions/dt=2026-08-16/hh=02/vehicle_positions-<ts>.jsonl.gz
└── gtfs/gtfs_bus-2026-08-16-<etag>.zip
```

## How the two processes coordinate

The recorder writes to `vehicle_positions-<timestamp>.jsonl.partial` while a file is open, then renames it to `.jsonl` when finished. The uploader only ever looks at `.jsonl` files.

Renaming a file within a directory is atomic, so a file is never visible in a half-renamed state. Either process can crash, restart, or be stopped independently and the other keeps working.

This also decouples their failure modes. If Cloud Storage is unreachable, the recorder keeps collecting to disk and the uploader drains the backlog when it recovers. Collection never depends on upload succeeding.

## Knowing when it breaks

Everything above handles a *process* failing. Nothing in a process can detect its own absence, or notice that it is connected to a feed which has quietly stopped sending. So the recorder pings a monitoring service every time it finishes a file. If those pings stop, an alert goes out.

The ping fires when a file is finished, not on a timer. A timer would only prove the process is running. Finishing a file proves the whole chain worked: connected, received data, wrote it, closed it.

The status badge on the main page is another signal.

## Security

The instance has its own identity with permission to write to one bucket and nothing else. Credentials are issued automatically and expire on their own, so there is no key file on the machine, nothing to rotate, and nothing to leak if the instance were compromised.

The one genuine secret, the monitoring URL, lives in a root-owned file outside the repository.

## Deploying a change

Push to `main`:

```bash
gcloud compute ssh howlate-collector --zone=us-west1-b --command="
  sudo git -C /opt/howlate/repo fetch origin &&
  sudo git -C /opt/howlate/repo reset --hard origin/main &&
  sudo bash /opt/howlate/repo/deploy/setup.sh
"
```

Continuous deployment is worth building when deploys are frequent. This one changes rarely, so a command is cheaper than a pipeline.
