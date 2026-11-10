#!/usr/bin/env bash
# Build the pipeline image and run `daily` every morning as a Cloud Run job.
#
#   bash pipeline/deploy/daily.sh
#
# Run it from a terminal, on a commit on release/ or main, after setup.sh.
#
# The first time, it asks for the healthchecks.io ping URL at a hidden prompt
# and stores it in Secret Manager. The URL never appears on a command line, in
# shell history, or in the repo, and nothing here reads it back.
#
# The job grades the last seven days, and two processes grading the same day at
# once can interleave their uploads, so the daily job and a backfill must never
# overlap. This script refuses to deploy while the backfill VM is running,
# checking at the start and again just before it schedules the job, and
# backfill-vm.sh refuses to start while this schedule is enabled or a daily run
# is unfinished. A daily run started by hand is not guarded: check first that
# no backfill VM is running.
#
# Rerunning it is safe. Creates are skipped when the thing exists, an image
# already built for this commit is reused, deploys replace the job's settings,
# and IAM bindings are additive.

set -euo pipefail

PROJECT=howlate-la
REGION=us-west1
JOB=howlate-daily
SECRET=howlate-daily-heartbeat
IMAGE="$REGION-docker.pkg.dev/$PROJECT/howlate/pipeline"
PIPELINE="howlate-pipeline@$PROJECT.iam.gserviceaccount.com"
INVOKER="howlate-scheduler@$PROJECT.iam.gserviceaccount.com"

# The image is built from the commit, not the working tree, so its tag names
# exactly the code inside it.
if [ -n "$(git status --porcelain -- pipeline .dockerignore)" ]; then
  echo "pipeline/ has uncommitted changes; commit them first" >&2
  exit 1
fi
TAG=$(git rev-parse --short=12 HEAD)

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

no_backfill() {
  local status
  status=$(lookup gcloud compute instances describe howlate-backfill --project "$PROJECT" \
    --zone us-west1-b --format 'value(status)')
  if [ -n "$status" ] && [ "$status" != TERMINATED ]; then
    echo "the backfill VM is $status; deploy once it has powered off" >&2
    exit 1
  fi
}
no_backfill

echo "==> APIs"
gcloud services enable run.googleapis.com cloudscheduler.googleapis.com \
  artifactregistry.googleapis.com cloudbuild.googleapis.com \
  secretmanager.googleapis.com --project "$PROJECT"

echo "==> Heartbeat secret $SECRET"
if ! gcloud secrets describe "$SECRET" --project "$PROJECT" >/dev/null 2>&1; then
  gcloud secrets create "$SECRET" --project "$PROJECT" --replication-policy automatic
fi
# Checked by its versions, never read: reading it would print the URL. Listed
# on its own line so that a failed listing stops the script, rather than
# reading as "empty" and asking for a URL that would replace a working one.
VERSIONS=$(gcloud secrets versions list "$SECRET" --project "$PROJECT" \
  --filter state=ENABLED --limit 1 --format 'value(name)')
if [ -z "$VERSIONS" ]; then
  if [ ! -t 0 ]; then
    echo "    $SECRET is empty; run this from a terminal to enter the URL" >&2
    exit 1
  fi
  read -rsp "    healthchecks.io ping URL (hidden): " URL
  echo
  case "$URL" in
    https://*) ;;
    *) echo "    expected a URL starting https://" >&2; exit 1 ;;
  esac
  # printf is a shell builtin, so the URL is in no process's arguments, and
  # '%s' adds no trailing newline.
  printf '%s' "$URL" | gcloud secrets versions add "$SECRET" --project "$PROJECT" \
    --data-file=- >/dev/null
  unset URL
fi
gcloud secrets add-iam-policy-binding "$SECRET" --project "$PROJECT" \
  --member "serviceAccount:$PIPELINE" --role roles/secretmanager.secretAccessor >/dev/null

echo "==> Image repository"
if ! gcloud artifacts repositories describe howlate --project "$PROJECT" \
    --location "$REGION" >/dev/null 2>&1; then
  gcloud artifacts repositories create howlate --project "$PROJECT" \
    --location "$REGION" --repository-format docker \
    --description "HowLate pipeline images"
fi

echo "==> Image $IMAGE:$TAG"
# Built once per commit. Rebuilding would push the tag again with a new
# digest, and the tag would stop naming one image.
if ! gcloud artifacts docker images describe "$IMAGE:$TAG" >/dev/null 2>&1; then
  CONTEXT=$(mktemp -d)
  trap 'rm -rf "$CONTEXT"' EXIT
  git archive HEAD pipeline .dockerignore | tar -x -C "$CONTEXT"
  cat >"$CONTEXT/cloudbuild.yaml" <<YAML
steps:
  - name: gcr.io/cloud-builders/docker
    args: [build, --platform, linux/amd64, -f, pipeline/Dockerfile, -t, "$IMAGE:$TAG", .]
images: ["$IMAGE:$TAG"]
YAML
  gcloud builds submit "$CONTEXT" --project "$PROJECT" --region "$REGION" \
    --config "$CONTEXT/cloudbuild.yaml"
fi
# Deployed by digest: a tag can be pushed again with other contents, a digest
# cannot.
DIGEST=$(gcloud artifacts docker images describe "$IMAGE:$TAG" \
  --format 'value(image_summary.digest)')

echo "==> Cloud Run job $JOB at $DIGEST"
# Memory. /work is memory on Cloud Run and holds the raw cache (three UTC
# partitions, about 3 GB, and up to five when a failed day is retried ahead of
# newer ones, because days already done are skipped without pruning), the
# unpacked timetables (about 0.3 GB, more when an
# older copy is tried), every graded day fetched for the site build (6.7 MB
# for 2026-08-27, so about 2.5 GB after a year), and DuckDB's spill files.
# DuckDB's own limit is 8 GB, so today even the five-partition case, about
# 14 GB, fits in 16 GiB; left unset, DuckDB would take 80% of the whole limit. The
# fetched days grow, so this budget needs another look within the year.
#
# --max-retries 0: when a run saves yesterday's report but fails its checks or
# a later step, a retry would find yesterday done, rebuild the site and ping
# success, clearing the /fail the first run sent.
gcloud run jobs deploy "$JOB" --project "$PROJECT" --region "$REGION" \
  --image "$IMAGE@$DIGEST" \
  --service-account "$PIPELINE" \
  --cpu 4 --memory 16Gi \
  --tasks 1 --max-retries 0 --task-timeout 3h \
  --args daily \
  --set-env-vars "HOWLATE_DUCKDB_MEMORY_LIMIT=8GB,HOWLATE_DUCKDB_TEMP_DIRECTORY=/work/.spill" \
  --set-secrets "HOWLATE_HEARTBEAT_URL=$SECRET:latest" \
  --labels "commit=$TAG"

echo "==> Scheduler identity $INVOKER"
if ! gcloud iam service-accounts describe "$INVOKER" --project "$PROJECT" >/dev/null 2>&1; then
  gcloud iam service-accounts create howlate-scheduler --project "$PROJECT" \
    --display-name "HowLate scheduler" \
    --description "Starts the howlate-daily job, and nothing else"
fi
# Invoker on this one job, not the project, so the scheduler can start the
# daily run and no other job.
# A new account can take a minute or more before IAM accepts it, so the
# binding is retried, and the last try shows its error.
invoker() {
  gcloud run jobs add-iam-policy-binding "$JOB" --project "$PROJECT" --region "$REGION" \
    --member "serviceAccount:$INVOKER" --role roles/run.invoker >/dev/null
}
bound=
for attempt in 1 2 3 4 5 6; do
  if invoker 2>/dev/null; then bound=1; break; fi
  echo "    not accepted yet, retrying in 20s ($attempt/6)"
  sleep 20
done
[ -n "$bound" ] || invoker

# Again, because a backfill could have started during the build.
no_backfill

echo "==> Schedule: 05:00 America/Los_Angeles"
# By 05:00 the service day two days back is complete, which is the last day
# `daily` grades. No retries: the run call returns at once, and a retry after
# a run that did start would grade the same days twice at the same time.
# A run that never starts is caught by healthchecks.io's silence alarm.
SCHEDULE=(--project "$PROJECT" --location "$REGION"
  --schedule "0 5 * * *" --time-zone America/Los_Angeles
  --uri "https://run.googleapis.com/v2/projects/$PROJECT/locations/$REGION/jobs/$JOB:run"
  --http-method POST --oauth-service-account-email "$INVOKER"
  --max-retry-attempts 0)
if gcloud scheduler jobs describe "$JOB" --project "$PROJECT" --location "$REGION" >/dev/null 2>&1; then
  gcloud scheduler jobs update http "$JOB" "${SCHEDULE[@]}"
else
  gcloud scheduler jobs create http "$JOB" "${SCHEDULE[@]}"
fi

# By hand, keep clear of 05:00 and of any backfill: a first run grades all
# seven days, and nothing else may grade them while it is still going.
echo "==> Deployed $TAG. Run it once by hand, not near 05:00 Pacific and never"
echo "    while the backfill VM is running, and watch it:"
echo "    gcloud run jobs execute $JOB --project $PROJECT --region $REGION --wait"
echo "    gcloud storage cat gs://howlate-derived/site/current.json"
