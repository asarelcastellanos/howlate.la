"""Copy a published site run from the derived bucket to Cloudflare R2.

The site fetches its JSON from R2 at runtime. Cloud Storage egress costs $0.12/GB
with no useful free allowance (see aggregate.upload), and R2 charges nothing for
egress. A run is about 117 files and 20 MB, so one copy a day moves about 0.6 GB
a month out of Google Cloud, which is cents.

The copy reads gs://howlate-derived and writes R2. It never touches
gs://howlate-raw. R2 holds nothing that cannot be rebuilt from the derived
bucket, so every write here is safe to repeat.

After a copy that moved R2's pointer, the daily job fetches the public address
from outside and checks that readers would see the new run; see `probe`.

R2 speaks the S3 protocol, so the client is boto3. Credentials come from the
environment and are never printed; see `from_env`.
"""

import json
import os
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

import boto3
from botocore.config import Config as ClientConfig
from botocore.exceptions import ClientError
from google.cloud import storage

from howlate_pipeline import DERIVED_BUCKET
from howlate_pipeline.aggregate import POINTER

REQUIRED = ("R2_ENDPOINT", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY")
DEFAULT_BUCKET = "howlate"
HOSTNAME = re.compile(r"[A-Za-z0-9.-]+")

# Run files never change once written, so browsers and the CDN may keep them for
# a year. The pointer is the one file that moves, so it lives for a minute: a
# new run reaches every browser within that minute.
RUN_CACHE = "public, max-age=31536000, immutable"
POINTER_CACHE = "public, max-age=60"

TRUE = {"1", "true", "yes"}
# The public status may trail the newest graded day by this many days. The job
# grades up to two days back and the site is rebuilt from finished days only,
# so a day or two of difference is normal and three is not.
MAX_LAG_DAYS = 2
FETCH_TIMEOUT = 10
RETRY_PAUSE = 2
RUN_PREFIX = re.compile(r"site/runs/[A-Za-z0-9._-]+/")


class Notice(RuntimeError):
    """A failure whose message this module wrote, so it is safe to print and ping.

    `describe` keeps only the class name of any other exception, because their
    text can hold the endpoint or a credential. A Notice never does: it names a
    variable or a file path and never a host, key or URL.
    """


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

    The endpoint holds the Cloudflare account id, so an invalid one is rejected
    here with a message that does not repeat it. Left to botocore, a malformed
    value fails later with "Invalid endpoint: <url>".
    """
    values = {name: env.get(name, "").strip() for name in REQUIRED}
    if not any(values.values()):
        return None
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise ValueError(f"R2 is partly configured; missing {', '.join(missing)}")
    if not is_https_address(values["R2_ENDPOINT"]):
        raise ValueError("R2_ENDPOINT is not a valid https address")
    return Config(
        endpoint=values["R2_ENDPOINT"],
        access_key_id=values["R2_ACCESS_KEY_ID"],
        secret_access_key=values["R2_SECRET_ACCESS_KEY"],
        bucket=env.get("R2_BUCKET", "").strip() or DEFAULT_BUCKET,
    )


def is_required(env: Mapping[str, str] = os.environ) -> bool:
    """True when R2_REQUIRED is 1, true or yes. The deployed job sets it; local runs do not."""
    return env.get("R2_REQUIRED", "").strip().lower() in TRUE


def public_url_from_env(env: Mapping[str, str] = os.environ) -> str | None:
    """The public data address, None when R2_PUBLIC_URL is unset.

    Checked like the endpoint, and rejected without echoing it. It is not
    secret, but the failure goes to a third party with the same wording.
    """
    value = env.get("R2_PUBLIC_URL", "").strip()
    if not value:
        return None
    if not is_https_address(value):
        raise Notice("R2_PUBLIC_URL is not a valid https address")
    return value


def is_https_address(endpoint: str) -> bool:
    """True for https://<hostname> with no port, userinfo, path, query or fragment.

    The hostname may hold only letters, digits, dots and hyphens, which rules out
    the underscores and spaces that botocore refuses.
    """
    try:
        parts = urlsplit(endpoint)
        hostname = parts.hostname
    except ValueError:
        return False
    return (
        parts.scheme == "https"
        and hostname is not None
        and HOSTNAME.fullmatch(hostname) is not None
        and parts.netloc.lower() == hostname
        and not (parts.path or parts.query or parts.fragment)
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
    """What went wrong, with no URL, account id or credential in it.

    botocore puts the endpoint URL, which holds the Cloudflare account id, in
    its messages, and google-auth puts the service account email in its own. A
    ClientError keeps only its code and the call. Any other exception keeps only
    its class name, because the text of an exception this code did not raise is
    not under its control.
    """
    if isinstance(error, Notice):
        return str(error)
    if isinstance(error, ClientError):
        return f"{error.response['Error'].get('Code')} during {error.operation_name}"
    return type(error).__name__


def read_pointer(derived: storage.Bucket) -> tuple[bytes, dict]:
    blob = derived.get_blob(POINTER)
    if blob is None:
        raise RuntimeError(f"gs://{DERIVED_BUCKET}/{POINTER} does not exist; nothing is published")
    body = blob.download_as_bytes()
    return body, json.loads(body)


def check_complete(run: str, blobs: list, record: dict) -> None:
    if len(blobs) != record["files"]:
        raise RuntimeError(f"{run} lists {len(blobs)} files but its pointer says {record['files']}")


def publish(gcs: storage.Client, s3, bucket: str, run: str | None = None) -> tuple[int, bool]:
    """Copy one run to R2, then move R2's pointer to it.

    `run` defaults to the run the derived bucket's pointer names. Returns the
    number of files copied and whether R2's pointer now names this run.

    Every file goes up before the pointer, and the pointer is written last, as
    in aggregate.upload. A copy that dies partway leaves R2's pointer on the
    previous complete run, and a reader never sees a mix of two. The files of a
    half-copied run stay in R2 until a later run prunes them.

    R2's pointer moves only when the derived pointer, read again after the copy,
    still names this run and counts the files that were copied. That catches a
    run whose upload finished while the copy ran. It cannot make the pointer
    write atomic. A newer run published between that read and the write is not
    seen, and R2's pointer then names this run until the next daily copy.
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
    if run == record["run"]:
        check_complete(run, blobs, record)

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
    # The first read may have named an older run, which skipped the count check
    # above. This run's upload can finish while the copy runs, so the listing may
    # predate files the pointer now counts. Checking again keeps R2's pointer off
    # a run that is missing files.
    check_complete(run, blobs, record)
    # The run R2's readers were just told about must outlive this copy. A reader
    # may have fetched the old pointer up to a minute ago and still be loading
    # that run's files. Without this, a run that fell out of the derived pointer's
    # `previous` list would be deleted the moment R2's pointer moved off it.
    r2_keep = r2_pointer_runs(s3, bucket)
    s3.put_object(
        Bucket=bucket,
        Key=POINTER,
        Body=body,
        ContentType="application/json",
        CacheControl=POINTER_CACHE,
    )

    try:
        prune(s3, bucket, run, {run, *record.get("previous", []), *r2_keep})
    except Exception as error:
        # Listing failed. The site is published; the next copy prunes.
        print(f"  could not prune old R2 runs: {describe(error)}")
    return len(blobs), True


def r2_pointer_runs(s3, bucket: str) -> set[str]:
    """The runs R2's pointer names: its `run` and its `previous` list.

    An empty set when there is no pointer yet. Any other failure also gives an
    empty set, because a copy should not fail for lack of a keep list; the cost
    is that a reader still on the old pointer may lose its run a copy early.
    """
    try:
        record = json.loads(s3.get_object(Bucket=bucket, Key=POINTER)["Body"].read())
        return {record["run"], *record.get("previous", [])}
    except ClientError as error:
        code = error.response["Error"].get("Code")
        status = error.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if code == "NoSuchKey" or str(code) == "404" or status == 404:
            return set()
        print(f"  could not read R2 pointer: {describe(error)}")
    except Exception as error:
        print(f"  could not read R2 pointer: {describe(error)}")
    return set()


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


def fetch_public(url: str) -> tuple[int, bytes]:
    """GET a public URL and return its status and body, trying twice.

    An error status is returned, not raised, so the probe can name it. An attempt
    that raises or does not return 200 waits a moment and tries once more, because
    one dropped connection should not fail the day's run. After the second
    attempt, an error status is returned and an exception is raised.
    """
    request = urllib.request.Request(url, headers={"User-Agent": "howlate-daily"})

    def once() -> tuple[int, bytes]:
        try:
            with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as error:
            return error.code, b""

    try:
        first = once()
        if first[0] == 200:
            return first
    except Exception:
        pass
    time.sleep(RETRY_PAUSE)
    return once()


def probe(base: str, run: str, last_day: str, fetch: Callable[[str], tuple[int, bytes]]) -> None:
    """Check the public data from the outside. Raises Notice naming the check that failed.

    The copy writes R2 with credentials, so it cannot see a broken CORS rule, a
    custom domain that points elsewhere, or a deleted run. This reads the same
    files a browser would: the pointer, then the status file it names.

    The pointer is requested with the time as its query. It is served with a
    60 second cache, so a fixed address could return the previous pointer from an
    edge cache and read as stale. A pointer that names this run or a newer one
    passes, because a newer run may have been published while this one copied.
    Run names sort by age. The status file must be within MAX_LAG_DAYS of
    `last_day`, the newest day the job just built.

    Messages carry file paths and run names, never the host.
    """

    def get(path: str, query: str = "") -> dict:
        try:
            status, body = fetch(f"{base}/{path}{query}")
        except Exception as error:
            raise Notice(
                f"R2 public check failed: could not fetch {path} ({describe(error)})"
            ) from None
        if status != 200:
            raise Notice(f"R2 public check failed: {path} returned {status}")
        try:
            data = json.loads(body)
        except ValueError:
            raise Notice(f"R2 public check failed: {path} is not JSON") from None
        if not isinstance(data, dict):
            raise Notice(f"R2 public check failed: {path} is not a JSON object")
        return data

    pointer = get("site/current.json", f"?nocache={int(time.time())}")
    named, prefix = pointer.get("run"), pointer.get("prefix")
    if not (
        isinstance(named, str)
        and isinstance(prefix, str)
        and RUN_PREFIX.fullmatch(prefix)
        and prefix == f"site/runs/{named}/"
    ):
        raise Notice("R2 public check failed: site/current.json has no usable run and prefix")
    if named < run:
        raise Notice(
            f"R2 public check failed: site/current.json names {named}, older than the copied {run}"
        )

    newest = date.fromisoformat(last_day)
    path = f"{prefix}status.json"
    seen = get(path).get("last_day")
    try:
        behind = (newest - date.fromisoformat(seen)).days
    except (TypeError, ValueError):
        raise Notice(f"R2 public check failed: {path} has no valid last_day") from None
    if behind > MAX_LAG_DAYS:
        raise Notice(
            f"R2 public check failed: {path} last_day {seen} is {behind} days behind {last_day}"
        )


def copy_if_configured(
    gcs: storage.Client,
    run: str | None = None,
    env: Mapping[str, str] = os.environ,
    s3=None,
    site_dir: Path | None = None,
    fetch: Callable[[str], tuple[int, bytes]] = fetch_public,
) -> bool:
    """Copy a run to R2 if the environment names an R2 bucket. False when it does not.

    With R2_REQUIRED set, missing settings raise a Notice instead of skipping,
    so a deploy that lost them cannot read as a clean run.

    When the copy moves R2's pointer and `site_dir` is given, the public address
    is then probed against the `status.json` in `site_dir`. The probe is skipped
    when R2_PUBLIC_URL is unset, and raises when it is unset and R2_REQUIRED is
    set. A pointer left alone because a newer run appeared is not probed: R2
    still serves the older run, which is not a fault of this copy.
    """
    config = from_env(env)
    if config is None:
        if is_required(env):
            raise Notice(
                "R2 copy not run: R2_REQUIRED is set but the R2 settings are not, "
                "so the public site would go stale"
            )
        print("  R2 copy skipped: R2_ENDPOINT, R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY not set")
        return False
    # Resolved here, not inside publish, so the probe knows which run it is judging.
    run = run or read_pointer(gcs.bucket(DERIVED_BUCKET))[1]["run"]
    count, moved = publish(gcs, s3 or make_client(config), config.bucket, run)
    where = "and moved the pointer" if moved else "but left the pointer"
    print(f"  copied {count} files to R2 bucket {config.bucket}, {where}")

    if not moved:
        print("  R2 freshness check skipped: R2's pointer was left alone")
        return True
    base = public_url_from_env(env)
    if base is None:
        if is_required(env):
            raise Notice(
                "R2 public check not run: R2_REQUIRED is set but R2_PUBLIC_URL is not, "
                "so a stale public site would go unseen"
            )
        print("  R2 freshness check skipped: R2_PUBLIC_URL not set")
        return True
    if site_dir is None:
        print("  R2 freshness check skipped: no built site to compare with")
        return True
    probe(base, run, json.loads((site_dir / "status.json").read_text())["last_day"], fetch)
    print("  R2 freshness check passed")
    return True
