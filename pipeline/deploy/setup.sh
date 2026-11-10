#!/usr/bin/env bash
# The pipeline's identity in Google Cloud: one service account that can read
# the raw archive and write the derived bucket, and nothing else.
#
#   bash pipeline/deploy/setup.sh
#
# Idempotent: every step checks before it creates, and IAM bindings are
# additive, so rerunning it changes nothing that is already right.
#
# The account is the pipeline's alone, separate from howlate-collector. The
# collector is the one place a mistake loses data for good, so nothing else
# borrows its identity or its write access to gs://howlate-raw.

set -euo pipefail

PROJECT=howlate-la
ACCOUNT=howlate-pipeline
EMAIL="$ACCOUNT@$PROJECT.iam.gserviceaccount.com"

# A new service account can take a minute or more before IAM accepts it in a
# binding, so each binding is retried rather than failing the first run.
bind() {
  local bucket=$1 role=$2
  for attempt in 1 2 3 4 5 6; do
    if gcloud storage buckets add-iam-policy-binding "$bucket" \
        --member "serviceAccount:$EMAIL" --role "$role" >/dev/null 2>&1; then
      return 0
    fi
    echo "    not accepted yet, retrying in 20s ($attempt/6)"
    sleep 20
  done
  gcloud storage buckets add-iam-policy-binding "$bucket" \
    --member "serviceAccount:$EMAIL" --role "$role" >/dev/null
}

echo "==> Service account $EMAIL"
if ! gcloud iam service-accounts describe "$EMAIL" --project "$PROJECT" >/dev/null 2>&1; then
  gcloud iam service-accounts create "$ACCOUNT" --project "$PROJECT" \
    --display-name "HowLate pipeline" \
    --description "Grades days: reads gs://howlate-raw, writes gs://howlate-derived"
fi

# Read only. objectViewer lists and reads objects and can neither write nor
# delete, so no bug in the pipeline can touch the one archive that cannot be
# rebuilt.
echo "==> Read access to gs://howlate-raw"
bind gs://howlate-raw roles/storage.objectViewer

# Create, read, list and delete objects, because a rerun replaces a day by
# deleting its old files first. objectUser rather than objectAdmin: it cannot
# change object IAM or retention, which the pipeline never needs. Everything
# here can be rebuilt from the raw archive.
echo "==> Write access to gs://howlate-derived"
bind gs://howlate-derived roles/storage.objectUser

echo "==> Done. Roles held by $EMAIL:"
for bucket in gs://howlate-raw gs://howlate-derived; do
  roles=$(gcloud storage buckets get-iam-policy "$bucket" \
    --flatten='bindings[].members' \
    --filter="bindings.members:serviceAccount:$EMAIL" \
    --format='value(bindings.role)')
  echo "    $bucket: ${roles:-none}"
done
