# Deploying

The collector runs on one small virtual machine in Oregon. It listens to Metro's feed around the clock, writes what it hears to files, and uploads them to cloud storage.

This page covers how to get code onto that machine, and how to tell whether it is still working.

## The thing to understand first

There are three separate places involved: your laptop, GitHub, and the machine.

**Pushing code to GitHub does not change the machine.** Nothing connects the two. There is no webhook and no automatic deploy. GitHub is where the code lives; the machine is where it runs, and it only changes when you tell it to.

So updating the collector is always two steps. Push, then deploy.

## Updating the machine

Push to `main` first. Then tell the machine to fetch that code and restart:

```bash
gcloud compute ssh howlate-collector --zone=us-west1-b --command="
  sudo git -C /opt/howlate/repo fetch origin &&
  sudo git -C /opt/howlate/repo reset --hard origin/main &&
  sudo bash /opt/howlate/repo/deploy/setup.sh
"
```

The machine has its own copy of this repository, so this pulls into that copy and runs the setup script from there. To see exactly which version is deployed, ask it:

```bash
gcloud compute ssh howlate-collector --zone=us-west1-b \
  --command="git -C /opt/howlate/repo log -1 --oneline"
```

Restarting stops the recorder gently, which lets it finish the file it was writing before the new version takes over. Nothing in progress is lost.

## Setting up a machine from scratch

The setup script lives in this repository, so a brand new machine needs the repository before it can run it:

```bash
sudo apt-get update && sudo apt-get install -y git
sudo git clone https://github.com/asarelcastellanos/howlate.la.git /opt/howlate/repo
sudo bash /opt/howlate/repo/deploy/setup.sh
```

The script installs Python, creates a user with no login access for the collector to run as, sets up its dependencies, and starts everything. Running it again is safe and is exactly what an update does.

## What is actually running

Three things, managed by systemd, which is what Linux uses to keep programs running and restart them when they fail.

**The recorder** holds a connection to Metro open and writes every update it hears into files, starting a fresh file every five minutes. If it crashes, systemd starts it again five seconds later.

**The uploader** watches for finished files, compresses them, sends them to cloud storage, and deletes the local copy once the upload has succeeded. It never touches the live feed, so a storage problem cannot interrupt recording.

**The timetable check** runs every six hours. It asks Metro whether the published schedule has changed and saves a copy only if it has, so most runs transfer almost nothing.

## Settings

Anything that should not be in a public repository lives in `/etc/howlate/env` on the machine:

```
HOWLATE_HEARTBEAT_URL=https://hc-ping.com/...
```

That URL is what the recorder pings every time it finishes a file. A monitoring service watches for those pings and sends an email if they stop, which is how a silent failure gets noticed rather than discovered days later.

Treat the URL as a password. Anyone who has it can send fake pings and hide a real outage. The file is readable only by root.

If the file is missing entirely, the collector still runs normally. It just goes unwatched.

## Checking on it

Watch the recorder as it works:

```bash
gcloud compute ssh howlate-collector --zone=us-west1-b \
  --command="sudo journalctl -u howlate-record -f"
```

Confirm data is still arriving in storage:

```bash
gcloud storage ls "gs://howlate-raw/vehicle_positions/dt=$(date -u +%F)/"
```

See when the timetable will next be checked:

```bash
gcloud compute ssh howlate-collector --zone=us-west1-b \
  --command="systemctl list-timers howlate-timetable"
```

The status badge on the main page is the fastest check of all. Green means files are still being written.

## How it gets permission to write

The machine has an identity of its own, separate from any person, and that identity is allowed to write to one storage bucket and nothing else.

Google hands the machine short-lived credentials automatically, and the code picks them up without being told to. There is no password or key file anywhere on the machine, so there is nothing to leak and nothing to rotate.
