"""Copy a published site run from the derived bucket to Cloudflare R2.

The site fetches its JSON from R2 at runtime. Cloud Storage egress costs $0.12/GB
with no useful free allowance (see aggregate.upload), and R2 charges nothing for
egress. A run is about 117 files and 20 MB, so one copy a day moves about 0.6 GB
a month out of Google Cloud, which is cents.

The copy reads gs://howlate-derived and writes R2. It never touches
gs://howlate-raw. R2 holds nothing that cannot be rebuilt from the derived
bucket, so every write here is safe to repeat.

R2 speaks the S3 protocol, so the client is boto3. Credentials come from the
environment and are never printed; see `from_env`.
"""

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass, field

import boto3
from botocore.config import Config as ClientConfig
from botocore.exceptions import BotoCoreError, ClientError
from google.cloud import storage

from howlate_pipeline import DERIVED_BUCKET
from howlate_pipeline.aggregate import POINTER

REQUIRED = ("R2_ENDPOINT", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY")
DEFAULT_BUCKET = "howlate"

# Run files never change once written, so browsers and the CDN may keep them for
# a year. The pointer is the one file that moves, so it lives for a minute: a
# new run reaches every browser within that minute.
RUN_CACHE = "public, max-age=31536000, immutable"
POINTER_CACHE = "public, max-age=60"


@dataclass(frozen=True)
class Config:
    endpoint: str
    access_key_id: str = field(repr=False)
    secret_access_key: str = field(repr=False)
    bucket: str


def from_env(env: Mapping[str, str] = os.environ) -> Config | None:
    """The R2 settings, None when none are set, an error when only some are.

    None means "not configured", which is how local runs and tests skip R2. A
    half-set environment is a deployment mistake, and skipping it would leave
    the public site stale with nothing to say so. R2_BUCKET is optional and does
    not count as a setting, so a job that sets only the bucket still skips.
    """
    values = {name: env.get(name, "").strip() for name in REQUIRED}
    if not any(values.values()):
        return None
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise ValueError(f"R2 is partly configured; missing {', '.join(missing)}")
    if not values["R2_ENDPOINT"].startswith("https://"):
        raise ValueError("R2_ENDPOINT must start with https://")
    return Config(
        endpoint=values["R2_ENDPOINT"],
        access_key_id=values["R2_ACCESS_KEY_ID"],
        secret_access_key=values["R2_SECRET_ACCESS_KEY"],
        bucket=env.get("R2_BUCKET", "").strip() or DEFAULT_BUCKET,
    )


def make_client(config: Config):
    """A boto3 S3 client for R2.

    Retries are boto3's standard mode: at most 4 attempts per call, backing off
    with jitter, on timeouts, dropped connections, 5xx and throttling. A 403 or
    404 is not retried. The timeouts keep one stuck call from holding a job that
    has a 3 hour limit. Checksums are sent only where S3 requires them, because
    boto3 1.36 and later add a CRC32 header to every upload that some S3-compatible
    stores reject.
    """
    return boto3.client(
        "s3",
        endpoint_url=config.endpoint,
        aws_access_key_id=config.access_key_id,
        aws_secret_access_key=config.secret_access_key,
        region_name="auto",
        config=ClientConfig(
            retries={"total_max_attempts": 4, "mode": "standard"},
            connect_timeout=10,
            read_timeout=60,
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        ),
    )


def describe(error: Exception) -> str:
    """What went wrong, safe to log and to send to healthchecks.io.

    botocore puts the endpoint URL, which holds the Cloudflare account id, in
    its messages. Only the error code and the call are kept.
    """
    if isinstance(error, ClientError):
        return f"{error.response['Error'].get('Code')} during {error.operation_name}"
    if isinstance(error, BotoCoreError):
        return type(error).__name__
    return repr(error)


def read_pointer(derived: storage.Bucket) -> tuple[bytes, dict]:
    blob = derived.get_blob(POINTER)
    if blob is None:
        raise RuntimeError(f"gs://{DERIVED_BUCKET}/{POINTER} does not exist; nothing is published")
    body = blob.download_as_bytes()
    return body, json.loads(body)


def publish(gcs: storage.Client, s3, bucket: str, run: str | None = None) -> tuple[int, bool]:
    """Copy one run to R2, then move R2's pointer to it.

    `run` defaults to the run the derived bucket's pointer names. Returns the
    number of files copied and whether R2's pointer now names this run.

    Every file goes up before the pointer, and the pointer is written last, as
    in aggregate.upload. A copy that dies partway leaves R2's pointer on the
    previous complete run, and a reader never sees a mix of two. The files of a
    half-copied run stay in R2 until a later run prunes them.
    """
    derived = gcs.bucket(DERIVED_BUCKET)
    _, record = read_pointer(derived)
    run = run or record["run"]
    prefix = f"site/runs/{run}/"
    blobs = sorted(gcs.list_blobs(DERIVED_BUCKET, prefix=prefix), key=lambda blob: blob.name)
    if not blobs:
        raise RuntimeError(f"gs://{DERIVED_BUCKET}/{prefix} holds no files")
    # The pointer counts the files of a complete run. A short listing means files
    # were pruned or are not visible yet, and copying them would publish a site
    # with holes.
    if run == record["run"] and len(blobs) != record["files"]:
        raise RuntimeError(f"{run} lists {len(blobs)} files but its pointer says {record['files']}")

    for blob in blobs:
        s3.put_object(
            Bucket=bucket,
            Key=blob.name,
            Body=blob.download_as_bytes(),
            ContentType="application/json",
            CacheControl=RUN_CACHE,
        )

    # Read again, not reused from above. A newer run may have been published
    # while this one was copying, and the daily job and a manual publish-r2 can
    # overlap. Writing this run's pointer then would move R2 back to an older
    # run. R2 has no conditional write here, so this narrows the race without
    # closing it; the next daily copy repairs a bad pointer within a day.
    body, record = read_pointer(derived)
    if record["run"] != run:
        print(f"  R2 pointer left alone: {POINTER} now names {record['run']}, not {run}")
        return len(blobs), False
    s3.put_object(
        Bucket=bucket,
        Key=POINTER,
        Body=body,
        ContentType="application/json",
        CacheControl=POINTER_CACHE,
    )

    try:
        prune(s3, bucket, run, {run, *record.get("previous", [])})
    except Exception as error:
        # Listing failed. The site is published; the next copy prunes.
        print(f"  could not prune old R2 runs: {describe(error)}")
    return len(blobs), True


def prune(s3, bucket: str, current: str, keep: set[str]) -> None:
    """Delete every run in R2 not in `keep`, as aggregate.prune does in the derived bucket.

    `keep` is the pointer's run and its `previous` list. Runs named after the
    current one are left alone, because another copy may still be uploading
    them. A failed delete is printed and left for the next copy.
    """
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix="site/"):
        for item in page.get("Contents", []):
            key = item["Key"]
            parts = key.split("/")
            if key == POINTER or (
                len(parts) > 3 and parts[1] == "runs" and (parts[2] in keep or parts[2] > current)
            ):
                continue
            try:
                s3.delete_object(Bucket=bucket, Key=key)
            except Exception as error:
                print(f"  could not delete R2 object {key}: {describe(error)}")


def copy_if_configured(
    gcs: storage.Client,
    run: str | None = None,
    env: Mapping[str, str] = os.environ,
    s3=None,
) -> bool:
    """Copy a run to R2 if the environment names an R2 bucket. False when it does not."""
    config = from_env(env)
    if config is None:
        print("  R2 copy skipped: R2_ENDPOINT, R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY not set")
        return False
    count, moved = publish(gcs, s3 or make_client(config), config.bucket, run)
    where = "and moved the pointer" if moved else "but left the pointer"
    print(f"  copied {count} files to R2 bucket {config.bucket}, {where}")
    return True
