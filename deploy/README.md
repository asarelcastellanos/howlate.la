# Deployment

HowLate collects continuously, so the interesting problems here are not about writing the collector. They are about keeping it alive for a month without anyone watching it.

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

Storage is one bucket. About 2 GB a month, and the instance is free-tier eligible, so the whole system runs for roughly the cost of nothing.

## Why a VM instead of Cloud Run

Cloud Run was the obvious first instinct and the wrong one.

Metro publishes over a **push websocket**, not an endpoint you poll. The collector holds a single connection open for weeks. That is not request-shaped work, so Cloud Run would mean pinning an instance with `min-instances=1` and CPU always allocated: an always-on container, plus a container build pipeline, to get exactly what a VM gives directly.

The timetable job genuinely is Cloud Run shaped, since it runs briefly and exits. It still lives on the VM, because standing up an image build, an artifact registry, a scheduler, and a second service account for a 40-line script that runs four times a day buys nothing while a machine is already running.

The general principle: pick infrastructure that matches the shape of the work, and resist adding a second deployment path until something actually needs it.

## How the two processes coordinate

They don't. That is the design.

The recorder writes to `vehicle_positions-<timestamp>.jsonl.partial` while a file is open, then renames it to `.jsonl` when finished. The uploader only ever looks at `.jsonl` files.

Renaming a file within a directory is atomic, so a file is never visible in a half-renamed state. No locks, no shared memory, no message queue, no coordination protocol to get wrong. Either process can crash, restart, or be stopped independently and the other keeps working.

This also decouples their failure modes. If Cloud Storage is unreachable, the recorder keeps collecting to disk and the uploader drains the backlog when it recovers. Collection never depends on upload succeeding.

## Designing for unattended operation

The collector ran correctly on a laptop long before it was ready to run alone. Most of the work was the difference between those two.

**Reconnection.** A single dropped connection would otherwise end the collection permanently. The recorder reconnects with exponential backoff capped at a minute, and deliberately keeps the current file open across brief drops. An earlier version closed on every disconnect, which turned a flapping link into 16 files of 3 records each instead of one clean file.

**Clean shutdown.** Every deploy stops the recorder. Handled carelessly, that leaves a half-written file behind each time. `SIGTERM` is handled explicitly rather than relying on Python exceptions, and the library's default 10 second disconnect timeout was reduced, since exceeding the service manager's patience gets the process killed outright. Measured stop time is under a second, with the open file properly finished.

**Crash recovery.** If the machine loses power, the in-progress file is left mid-write. On startup the recorder adopts any orphaned file so it still gets uploaded, rather than sitting on disk invisibly forever.

**Rotation on a clock, not on traffic.** Measuring the feed showed Metro sends in bursts: about 40 messages in under 10 milliseconds, then 1 to 4 seconds of silence. Rotating on message arrival inherits that raggedness, and during the overnight lull it would hold a file open for hours. Rotating on a timer means data reaches storage on schedule regardless of how the feed behaves.

## Knowing when it breaks

Everything above handles a *process* failing. Nothing in a process can detect its own absence, or notice that it is connected to a feed which has quietly stopped sending.

So the recorder pings a monitoring service every time it finishes a file. If those pings stop, an alert goes out. That is the only mechanism here that catches "the machine is gone" or "the connection is fine but nothing is arriving," and on a month-long collection it is the difference between losing fifteen minutes and losing a week.

The status badge on the main page is that signal, made public.

## Security posture

The instance has its own identity with permission to write to one bucket and nothing else. Credentials are issued automatically and expire on their own, so there is no key file on the machine, nothing to rotate, and nothing to leak if the instance were compromised.

The one genuine secret, the monitoring URL, lives in a root-owned file outside the repository. It is a write endpoint: anyone holding it could send fake heartbeats and hide a real outage.

## Deploying a change

Push to `main`, then tell the machine to pull and restart:

```bash
gcloud compute ssh howlate-collector --zone=us-west1-b --command="
  sudo git -C /opt/howlate/repo fetch origin &&
  sudo git -C /opt/howlate/repo reset --hard origin/main &&
  sudo bash /opt/howlate/repo/deploy/setup.sh
"
```

Pushing to GitHub does not update the machine. Nothing connects them, which is a deliberate choice: continuous deployment is worth building when deploys are frequent, and this one changes rarely.

Two mistakes worth recording, both caught by verifying rather than trusting:

`systemctl enable --now` only starts a unit that is stopped, so redeploys reported success while the old code kept running. It needed `restart`.

Bootstrapping the setup script from `raw.githubusercontent.com` served a cached copy several minutes stale, silently installing the previous version. Pulling into the machine's own clone made the deployed commit verifiable with `git log`.

Both were invisible from the deploy output. Checking what the running process actually had, rather than whether the service reported healthy, is what surfaced them.
