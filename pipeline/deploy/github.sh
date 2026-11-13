#!/usr/bin/env bash
# Let GitHub Actions deploy the pipeline image, with no key file anywhere.
#
#   bash pipeline/deploy/github.sh
#
# Run it after daily.sh, which creates the job and the image repository this
# grants access to. It sets up Workload Identity Federation: a push to main of
# this repository, running .github/workflows/deploy-pipeline.yml, gets a token
# from GitHub, and Google exchanges it for the howlate-deployer account. No
# other workflow, branch, event or repository passes the condition.
#
# The account can push images to the howlate repository, whose tags are made
# immutable so no push can move one; read and update the howlate-daily job,
# through a custom role holding only those two permissions, so it cannot run,
# delete or override the job; and act as howlate-pipeline, because updating a
# job means deploying code that runs as that account. Every grant is on that
# one resource, not the project.
#
# Rerunning it is safe: creates are skipped when the thing exists, and IAM
# bindings are additive.

set -euo pipefail

PROJECT=howlate-la
REGION=us-west1
NUMBER=712625281696
# The repository's numeric id, not its name: a deleted repository's name can
# be registered again by someone else, its id cannot.
REPOSITORY_ID=1334870365
WORKFLOW="asarelcastellanos/howlate.la/.github/workflows/deploy-pipeline.yml@refs/heads/main"
ROLE=howlateJobUpdater
POOL=github
PROVIDER=howlate-la
DEPLOYER="howlate-deployer@$PROJECT.iam.gserviceaccount.com"
PIPELINE="howlate-pipeline@$PROJECT.iam.gserviceaccount.com"

# A new account can take a minute or more before IAM accepts it, so each
# binding is retried, and the last try shows its error.
retry() {
  local attempt
  for attempt in 1 2 3 4 5 6; do
    "$@" >/dev/null 2>&1 && return 0
    echo "    not accepted yet, retrying in 20s ($attempt/6)"
    sleep 20
  done
  "$@" >/dev/null
}

if ! gcloud run jobs describe howlate-daily --project "$PROJECT" --region "$REGION" >/dev/null; then
  echo "howlate-daily does not exist yet; run pipeline/deploy/daily.sh first" >&2
  exit 1
fi

echo "==> APIs"
gcloud services enable iamcredentials.googleapis.com sts.googleapis.com --project "$PROJECT"

echo "==> Identity pool $POOL"
if ! gcloud iam workload-identity-pools describe "$POOL" --project "$PROJECT" \
    --location global >/dev/null 2>&1; then
  gcloud iam workload-identity-pools create "$POOL" --project "$PROJECT" \
    --location global --display-name "GitHub Actions"
fi

echo "==> Provider $PROVIDER"
# Only the deploy workflow, run by a push to main of this repository, passes.
# A pull request, another branch, a fork, or another workflow gets no token.
CONDITION="assertion.repository_id == '$REPOSITORY_ID' && assertion.ref == 'refs/heads/main' && assertion.event_name == 'push' && assertion.workflow_ref == '$WORKFLOW'"
if gcloud iam workload-identity-pools providers describe "$PROVIDER" --project "$PROJECT" \
    --location global --workload-identity-pool "$POOL" >/dev/null 2>&1; then
  # Rewritten every run, so a tightened condition reaches a provider that
  # already exists.
  gcloud iam workload-identity-pools providers update-oidc "$PROVIDER" --project "$PROJECT" \
    --location global --workload-identity-pool "$POOL" --attribute-condition "$CONDITION"
else
  gcloud iam workload-identity-pools providers create-oidc "$PROVIDER" --project "$PROJECT" \
    --location global --workload-identity-pool "$POOL" \
    --display-name "howlate.la main" \
    --issuer-uri https://token.actions.githubusercontent.com \
    --attribute-mapping "google.subject=assertion.sub,attribute.repository_id=assertion.repository_id" \
    --attribute-condition "$CONDITION"
fi

echo "==> Role $ROLE"
# run.developer would also let the account run, delete and override the job.
# Updating it needs only these two.
if ! gcloud iam roles describe "$ROLE" --project "$PROJECT" >/dev/null 2>&1; then
  gcloud iam roles create "$ROLE" --project "$PROJECT" \
    --title "HowLate job updater" --description "Read and update one Cloud Run job" \
    --permissions run.jobs.get,run.jobs.update --stage GA
fi

echo "==> Immutable image tags"
# A tag names the commit it was built from; no push may move it.
gcloud artifacts repositories update howlate --project "$PROJECT" --location "$REGION" \
  --immutable-tags >/dev/null

echo "==> Deploy account $DEPLOYER"
if ! gcloud iam service-accounts describe "$DEPLOYER" --project "$PROJECT" >/dev/null 2>&1; then
  gcloud iam service-accounts create howlate-deployer --project "$PROJECT" \
    --display-name "HowLate deployer" \
    --description "GitHub Actions: pushes the pipeline image and updates howlate-daily"
fi

echo "==> Who may become it"
retry gcloud iam service-accounts add-iam-policy-binding "$DEPLOYER" --project "$PROJECT" \
  --role roles/iam.workloadIdentityUser \
  --member "principalSet://iam.googleapis.com/projects/$NUMBER/locations/global/workloadIdentityPools/$POOL/attribute.repository_id/$REPOSITORY_ID"

echo "==> What it may do"
retry gcloud artifacts repositories add-iam-policy-binding howlate --project "$PROJECT" \
  --location "$REGION" --member "serviceAccount:$DEPLOYER" --role roles/artifactregistry.writer
retry gcloud run jobs add-iam-policy-binding howlate-daily --project "$PROJECT" \
  --region "$REGION" --member "serviceAccount:$DEPLOYER" --role "projects/$PROJECT/roles/$ROLE"
retry gcloud iam service-accounts add-iam-policy-binding "$PIPELINE" --project "$PROJECT" \
  --member "serviceAccount:$DEPLOYER" --role roles/iam.serviceAccountUser

echo "==> Done. The next push to main that changes pipeline/ deploys itself."
