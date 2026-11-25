#!/usr/bin/env bash
# Grade every collected day once, on a temporary VM beside the archive.
#
#   bash pipeline/deploy/backfill-vm.sh [--script <path> [--run <id>]] <git-ref> <first-day> [last-day]
#   bash pipeline/deploy/backfill-vm.sh release/v0.3.0 2026-08-18
#   bash pipeline/deploy/backfill-vm.sh --script pipeline/scripts/count_positions.py \
#     v0.5.2/vm-script-mode 2026-11-20 2026-11-20
#
# One date means through the latest complete service day, which can be several
# days of 1.2 GB each. Pass the last day too for a one-day run.
#
# With --script the VM runs that analysis script once per service day in place
# of `backfill`, in the same checkout and Python environment. The script is a
# repo-relative path under pipeline/ that ends in .py and exists at <git-ref>;
# it is checked before the VM is created. The contract for the script is
#
#   python <script> --service-date YYYYMMDD --cache <dir> --out <dir>
#
# It reads raw files through `arrivals.fetch_raw(client, service_date, cache)`,
# which is free on the VM, and writes its results under --out. After each day
# the VM copies that day's --out to
# gs://howlate-derived/logs/scripts/<script-name>/<run-id>/<day>/, then
# writes a `_done` object beside it, then clears the day's cache. The wrapper
# copies only under gs://howlate-derived/logs/scripts/. The script itself is
# trusted code. It runs with the pipeline service account, which can write
# anywhere in gs://howlate-derived and can only read gs://howlate-raw.
#
# A Spot reclaim deletes the VM, and nothing reboots it, so the day in progress
# is lost. Running this script again without --run starts the whole range over
# under a new run id. Running it with --run <id> reuses that id as the output
# prefix, and the new VM skips each day that has its `_done`. The script prints
# the run id and the exact resume command when a run starts. A day that fails
# shows only as "not saved" in the run log, so check the log and the `_done`
# objects. Script mode writes nowhere else: not gs://howlate-raw and not the
# arrivals/, trips/, reports/ or site/ prefixes.
#
# Why a VM: the raw archive is about 1.2 GB a day. Reading it from inside
# us-west1 is free; reading it to a laptop costs about $0.12/GB.
#
# Why Spot: it costs a fraction of a normal VM, and the backfill resumes where
# it stopped, so being reclaimed costs only the day in progress. Run this
# script again and the next VM picks up from there. Script mode needs --run
# to do the same.
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
# Progress shows on the serial console. The log is copied to
# gs://howlate-derived/logs/ when the run ends, and again, best effort, when the
# VM shuts down, including when Spot reclaims it. Google runs shutdown scripts
# only on a best-effort basis, so a reset or a host failure can lose the last
# copy.

set -euo pipefail

# True for a path the VM may run: inside pipeline/, ending in .py, made only of
# letters, digits, underscore, hyphen, dot and slash, with no `..` part that
# could climb out of it and no file name that starts with a dot. A comma would
# split `--metadata` and the name becomes part of the output prefix. Checked
# here because a bad path found on the VM costs a boot and a package install
# before it fails.
valid_script_path() {
  case "$1" in
    pipeline/*.py) ;;
    *) return 1 ;;
  esac
  case "$1" in
    *[!A-Za-z0-9_./-]*) return 1 ;;
  esac
  case "/$1" in
    */.[!/]*.py | */.py) return 1 ;;
  esac
  case "/$1/" in
    */../*) return 1 ;;
  esac
  return 0
}

# True for a run id that stays one path part of the output prefix and cannot
# break the comma-separated `--metadata`.
valid_run_id() {
  case "$1" in
    "" | *[!A-Za-z0-9_-]*) return 1 ;;
  esac
  return 0
}

SCRIPT_PATH=
RUN_ID=
while [ "${1:-}" = --script ] || [ "${1:-}" = --run ]; do
  if [ "$1" = --script ]; then
    SCRIPT_PATH=${2:?repo-relative path to a script under pipeline/, e.g. pipeline/scripts/count_positions.py}
  else
    RUN_ID=${2:?run id to resume, e.g. 20261122T180000Z}
  fi
  shift 2
done
if [ -n "$SCRIPT_PATH" ] && ! valid_script_path "$SCRIPT_PATH"; then
  echo "$SCRIPT_PATH must be under pipeline/, end in .py and use only letters, digits, _, -, . and /" >&2
  exit 1
fi
if [ -n "$RUN_ID" ]; then
  if [ -z "$SCRIPT_PATH" ]; then
    echo "--run needs --script" >&2
    exit 1
  fi
  if ! valid_run_id "$RUN_ID"; then
    echo "$RUN_ID must use only letters, digits, _ and -" >&2
    exit 1
  fi
fi

REF=${1:?git ref to run, e.g. release/v0.3.0}
FIRST=${2:?first service day, e.g. 2026-08-18}
# The latest complete service day in Los Angeles. Bus service runs to 05:45 the
# next morning and the last bus report of four measured days came at 06:12, so
# yesterday is complete from 07:00 and the day before it until then. This
# matches `yesterday()` in pipeline/src/howlate_pipeline/__main__.py.
if [ "$(TZ=America/Los_Angeles date +%H)" -ge 7 ]; then BACK=1; else BACK=2; fi
LAST=${3:-$(TZ=America/Los_Angeles date -v-"$BACK"d +%F 2>/dev/null || TZ=America/Los_Angeles date -d "$BACK days ago" +%F)}

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
# skips every day already in the bucket. A Spot reclaim deletes the VM instead
# of rebooting it, so a script run resumes only when this script is run again
# with --run and the same id.
set -uo pipefail
meta() { curl -sf -H "Metadata-Flavor: Google" \
  "http://metadata.google.internal/computeMetadata/v1/instance/attributes/$1"; }
REF=$(meta howlate-ref); FIRST=$(meta howlate-first); LAST=$(meta howlate-last)
# Absent in backfill mode, which leaves both empty. RUN is fixed when the VM is
# created, so a reboot resumes under the same prefix.
SCRIPT=$(meta howlate-script || true); RUN=$(meta howlate-run || true)
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
  if [ -z "$SCRIPT" ]; then
    echo "backfill $FIRST to $LAST at $(git -C /opt/howlate rev-parse --short HEAD)"
    cd /var/tmp && /opt/venv/bin/python -m howlate_pipeline backfill \
      --from "$FIRST" --to "$LAST" --cache /var/tmp/cache --out /var/tmp/out
    echo "exit $?"
  else
    echo "$SCRIPT $FIRST to $LAST at $(git -C /opt/howlate rev-parse --short HEAD)"
    NAME=$(basename "$SCRIPT" .py)
    PREFIX="gs://howlate-derived/logs/scripts/$NAME/$RUN"
    cd /var/tmp
    # The day list comes from the pipeline's own parser, so a date means here
    # what it means to `backfill`.
    for DAY in $(/opt/venv/bin/python -c 'import sys
from howlate_pipeline.backfill import days_between
print(*days_between(sys.argv[1], sys.argv[2]))' "$FIRST" "$LAST"); do
      # Written last, so a day cut off mid-copy has no marker and reruns.
      if gcloud storage ls "$PREFIX/$DAY/_done" >/dev/null 2>&1; then
        echo "$DAY already done, skipping"
        continue
      fi
      rm -rf "/var/tmp/out/$DAY"
      mkdir -p "/var/tmp/out/$DAY"
      /opt/venv/bin/python "/opt/howlate/$SCRIPT" --service-date "$DAY" \
        --cache /var/tmp/cache --out "/var/tmp/out/$DAY"
      CODE=$?
      echo "$DAY exit $CODE"
      if [ "$CODE" -eq 0 ] &&
        gcloud storage rsync -r "/var/tmp/out/$DAY" "$PREFIX/$DAY" &&
        echo done >/var/tmp/done-marker &&
        gcloud storage cp -q /var/tmp/done-marker "$PREFIX/$DAY/_done"; then
        echo "$DAY copied to $PREFIX/$DAY/"
      else
        echo "$DAY not saved"
      fi
      # The raw archive is about 1.2 GB a day and each day reads three
      # partitions, so a long range would fill the 50 GB disk if the cache were
      # kept. Refetching the overlap is free on the VM.
      rm -rf /var/tmp/cache "/var/tmp/out/$DAY"
    done
  fi
} 2>&1 | tee -a "$LOG"

gcloud storage cp -q "$LOG" "$(cat /var/tmp/howlate-log-url)" || true
shutdown -h now
SCRIPT

cat >"$SHUTDOWN" <<'SCRIPT'
#!/usr/bin/env bash
# Runs, best effort, when the VM shuts down, including when Spot reclaims it,
# which allows up to 30 seconds: enough for one small copy if it gets them.
[ -f /var/log/howlate-backfill.log ] && [ -f /var/tmp/howlate-log-url ] &&
  gcloud storage cp -q /var/log/howlate-backfill.log "$(cat /var/tmp/howlate-log-url)"
true
SCRIPT

# The daily job grades the last seven days. A backfill grading the same days
# at the same time could interleave their uploads, so the schedule must be
# paused first, no daily run may be unfinished, and the schedule is resumed
# once the backfill VM has powered off.
# Prints a field of a resource, or nothing when the resource does not exist,
# including when its API is still disabled. Any other error stops the script: a guard that read a permission error or an
# outage as "absent" would let two graders overlap.
lookup() {
  local err out
  err=$(mktemp)
  if out=$("$@" 2>"$err"); then
    rm -f "$err"
    printf '%s' "$out"
    return 0
  fi
  if grep -qiE 'not.?found|SERVICE_DISABLED' "$err"; then
    rm -f "$err"
    return 0
  fi
  cat "$err" >&2
  rm -f "$err"
  return 1
}

# Script mode skips these guards. It writes only under logs/scripts/, which the
# daily job never touches, so the two cannot interleave uploads. Backfill mode
# writes arrivals/, trips/ and reports/ and keeps every guard.
if [ -z "$SCRIPT_PATH" ]; then
  SCHEDULE=$(lookup gcloud scheduler jobs describe howlate-daily --project "$PROJECT" \
    --location us-west1 --format 'value(state)')
  if [ "$SCHEDULE" = ENABLED ]; then
    echo "the daily job's schedule is enabled. Pause it first:" >&2
    echo "  gcloud scheduler jobs pause howlate-daily --project $PROJECT --location us-west1" >&2
    echo "and resume it once the backfill VM has powered off:" >&2
    echo "  gcloud scheduler jobs resume howlate-daily --project $PROJECT --location us-west1" >&2
    exit 1
  fi
  # An execution with no completion time is still running.
  UNFINISHED=$(lookup gcloud run jobs executions list --job howlate-daily --project "$PROJECT" \
    --region us-west1 --format 'value(name,status.completionTime)' | awk -F '\t' '$2 == "" {print $1}')
  if [ -n "$UNFINISHED" ]; then
    echo "a daily run is unfinished ($UNFINISHED); wait for it to end" >&2
    exit 1
  fi
else
  # The script must exist at the ref the VM will clone, not only in this
  # checkout, so fetch that ref and look inside it.
  git fetch -q origin "$REF"
  if ! git cat-file -e "FETCH_HEAD:$SCRIPT_PATH" 2>/dev/null; then
    echo "$SCRIPT_PATH does not exist at $REF" >&2
    exit 1
  fi
fi

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
  # Its disk holds the last run's log, and the copies to the bucket can fail
  # without saying so. A stopped VM's serial console cannot be read, so show
  # the newest log the bucket has; if it is not from the last run, stop here
  # and recover the log from the disk before deleting.
  echo "==> Newest backfill logs in the bucket:"
  gcloud storage ls gs://howlate-derived/logs/ 2>/dev/null | tail -5 | sed 's/^/    /' || true
  NEWEST=$(gcloud storage ls gs://howlate-derived/logs/ 2>/dev/null | tail -1 || true)
  if [ -n "$NEWEST" ]; then
    echo "==> End of $NEWEST:"
    gcloud storage cat "$NEWEST" 2>/dev/null | tail -20 | sed 's/^/    /' || true
  fi
  echo "==> Deleting the powered-off $NAME from the last run"
  gcloud compute instances delete "$NAME" --project "$PROJECT" --zone "$ZONE" --quiet
fi

META="howlate-ref=$REF,howlate-first=$FIRST,howlate-last=$LAST"
if [ -n "$SCRIPT_PATH" ]; then
  RUN=${RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)}
  META="$META,howlate-script=$SCRIPT_PATH,howlate-run=$RUN"
  echo "==> Script $SCRIPT_PATH, $FIRST to $LAST, from $REF on $NAME"
  echo "    run id: $RUN"
  echo "    output: gs://howlate-derived/logs/scripts/$(basename "$SCRIPT_PATH" .py)/$RUN/"
  echo "    if Spot reclaims the VM, resume the days not yet done with:"
  echo "    bash pipeline/deploy/backfill-vm.sh --script $SCRIPT_PATH --run $RUN $REF $FIRST $LAST"
else
  echo "==> Backfill $FIRST to $LAST from $REF on $NAME"
fi
gcloud compute instances create "$NAME" --project "$PROJECT" --zone "$ZONE" \
  --machine-type e2-standard-8 \
  --provisioning-model SPOT --instance-termination-action DELETE \
  --max-run-duration 8h \
  --service-account "$EMAIL" --scopes cloud-platform \
  --image-family debian-12 --image-project debian-cloud \
  --boot-disk-size 50GB --boot-disk-type pd-balanced \
  --metadata "$META" \
  --metadata-from-file "startup-script=$STARTUP,shutdown-script=$SHUTDOWN"

echo "==> Started. Follow it with:"
echo "    gcloud compute instances get-serial-port-output $NAME --zone $ZONE | tail"
echo "    gcloud storage ls gs://howlate-derived/reports/v2/ | wc -l"
echo "  and delete it when it has powered off:"
echo "    gcloud compute instances delete $NAME --zone $ZONE"
