#!/usr/bin/env bash
# Grade every collected day once, on a temporary VM beside the archive.
#
#   bash pipeline/deploy/backfill-vm.sh <git-ref> <first-day> [last-day]
#   bash pipeline/deploy/backfill-vm.sh release/v0.3.0 2026-08-18
#
# Why a VM: the raw archive is about 1.2 GB a day. Reading it from inside
# us-west1 is free; reading it to a laptop costs about $0.12/GB.
#
# Why Spot: it costs a fraction of a normal VM, and the backfill resumes where
# it stopped, so being reclaimed costs only the day in progress. Run this
# script again and the next VM picks up from there.
#
# When the backfill ends the VM powers itself off. Powered off, it no longer
# bills for CPU but its 50 GB disk still bills, about $5 a month, until it is
# deleted. This script deletes a powered-off one before starting the next, and
# after a run it should be deleted by hand:
#
#   gcloud compute instances delete howlate-backfill --zone us-west1-b
#
# `--max-run-duration` deletes a VM still running after eight hours, and Spot
# deletes one it reclaims; powering off clears that timer.
#
# Progress shows on the serial console, and the log is copied to
# gs://howlate-derived/logs/ when the run ends and again when the VM shuts
# down for any reason, including Spot reclaiming it.

set -euo pipefail

REF=${1:?git ref to run, e.g. release/v0.3.0}
FIRST=${2:?first service day, e.g. 2026-08-18}
# Two days back in Los Angeles: a service day is complete only once the UTC
# partition after it has closed.
LAST=${3:-$(TZ=America/Los_Angeles date -v-2d +%F 2>/dev/null || TZ=America/Los_Angeles date -d "2 days ago" +%F)}

PROJECT=howlate-la
ZONE=us-west1-b
NAME=howlate-backfill
EMAIL="howlate-pipeline@$PROJECT.iam.gserviceaccount.com"

STARTUP=$(mktemp)
SHUTDOWN=$(mktemp)
trap 'rm -f "$STARTUP" "$SHUTDOWN"' EXIT

cat >"$STARTUP" <<'SCRIPT'
#!/usr/bin/env bash
# Runs as root on the VM at every boot. A reboot reruns the backfill, which
# skips every day already in the bucket.
set -uo pipefail
meta() { curl -sf -H "Metadata-Flavor: Google" \
  "http://metadata.google.internal/computeMetadata/v1/instance/attributes/$1"; }
REF=$(meta howlate-ref); FIRST=$(meta howlate-first); LAST=$(meta howlate-last)
LOG=/var/log/howlate-backfill.log
# One name per boot, written down so the shutdown script uploads to the same
# object instead of starting another.
echo "gs://howlate-derived/logs/backfill-$(date -u +%Y%m%dT%H%M%SZ).log" >/var/tmp/howlate-log-url
export PYTHONUNBUFFERED=1

# Through tee, so every line also reaches the serial console while it runs.
{
  apt-get update -qq && apt-get install -y -qq git python3-venv >/dev/null
  rm -rf /opt/howlate && git clone -q --branch "$REF" --depth 1 \
    https://github.com/asarelcastellanos/howlate.la /opt/howlate
  python3 -m venv /opt/venv && /opt/venv/bin/pip install -q /opt/howlate/pipeline
  echo "backfill $FIRST to $LAST at $(git -C /opt/howlate rev-parse --short HEAD)"
  cd /var/tmp && /opt/venv/bin/python -m howlate_pipeline backfill \
    --from "$FIRST" --to "$LAST" --cache /var/tmp/cache --out /var/tmp/out
  echo "exit $?"
} 2>&1 | tee -a "$LOG"

gcloud storage cp -q "$LOG" "$(cat /var/tmp/howlate-log-url)" || true
shutdown -h now
SCRIPT

cat >"$SHUTDOWN" <<'SCRIPT'
#!/usr/bin/env bash
# Runs on every shutdown, including Spot reclaiming the VM, which allows about
# 30 seconds: enough for one small copy.
[ -f /var/log/howlate-backfill.log ] && [ -f /var/tmp/howlate-log-url ] &&
  gcloud storage cp -q /var/log/howlate-backfill.log "$(cat /var/tmp/howlate-log-url)"
true
SCRIPT

# A finished run leaves its VM powered off. Delete it so this one can start;
# refuse if one is still running, since two backfills must not grade the same
# days at once.
STATUS=$(gcloud compute instances describe "$NAME" --project "$PROJECT" --zone "$ZONE" \
  --format='value(status)' 2>/dev/null || true)
if [ -n "$STATUS" ]; then
  if [ "$STATUS" != TERMINATED ]; then
    echo "$NAME is $STATUS; wait for it to finish or delete it first" >&2
    exit 1
  fi
  echo "==> Deleting the powered-off $NAME from the last run"
  gcloud compute instances delete "$NAME" --project "$PROJECT" --zone "$ZONE" --quiet
fi

echo "==> Backfill $FIRST to $LAST from $REF on $NAME"
gcloud compute instances create "$NAME" --project "$PROJECT" --zone "$ZONE" \
  --machine-type e2-standard-8 \
  --provisioning-model SPOT --instance-termination-action DELETE \
  --max-run-duration 8h \
  --service-account "$EMAIL" --scopes cloud-platform \
  --image-family debian-12 --image-project debian-cloud \
  --boot-disk-size 50GB --boot-disk-type pd-balanced \
  --metadata "howlate-ref=$REF,howlate-first=$FIRST,howlate-last=$LAST" \
  --metadata-from-file "startup-script=$STARTUP,shutdown-script=$SHUTDOWN"

echo "==> Started. Follow it with:"
echo "    gcloud compute instances get-serial-port-output $NAME --zone $ZONE | tail"
echo "    gcloud storage ls gs://howlate-derived/reports/v2/ | wc -l"
echo "  and delete it when it has powered off:"
echo "    gcloud compute instances delete $NAME --zone $ZONE"
