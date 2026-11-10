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
gcloud storage buckets add-iam-policy-binding gs://howlate-raw \
  --member "serviceAccount:$EMAIL" --role roles/storage.objectViewer >/dev/null

# Write and delete, because a rerun replaces a day by deleting its old files
# first. Everything here can be rebuilt from the raw archive.
echo "==> Write access to gs://howlate-derived"
gcloud storage buckets add-iam-policy-binding gs://howlate-derived \
  --member "serviceAccount:$EMAIL" --role roles/storage.objectAdmin >/dev/null

echo "==> Done"
gcloud storage buckets get-iam-policy gs://howlate-raw --format=json \
  | grep -A1 objectViewer | sed 's/^/    raw:     /'
gcloud storage buckets get-iam-policy gs://howlate-derived --format=json \
  | grep -A1 objectAdmin | sed 's/^/    derived: /'
