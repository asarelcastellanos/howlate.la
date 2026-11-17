"""Copying a published run to R2: order, headers, the pointer, pruning, and config.

No network. The derived bucket is test_write's fake and R2 is FakeS3 below, so
a test can see every object written and in what order.
"""

import io
import json
from pathlib import Path

import pytest
import test_write
from botocore.exceptions import ClientError

from howlate_pipeline import DERIVED_BUCKET, aggregate, r2

POINTER = "site/current.json"
OLD, NEW = "20261106T130000Z-aaaaaa", "20261107T130000Z-bbbbbb"


class Blob(test_write.FakeBlob):
    def download_as_bytes(self) -> bytes:
        return self.store[(self.bucket_name, self.name)]


class Bucket(test_write.FakeBucket):
    def blob(self, name):
        return Blob(self.name, name, self.store)

    def get_blob(self, name):
        return self.blob(name) if (self.name, name) in self.store else None


class Derived(test_write.FakeClient):
    """test_write's two buckets, with the downloads the copy needs."""

    def __init__(self):
        super().__init__([])

    def bucket(self, name):
        return Bucket(name, self.store)

    def list_blobs(self, bucket, prefix):
        return [
            Blob(b, n, self.store)
            for b, n in list(self.store)
            if b == bucket and n.startswith(prefix)
        ]


def publish_runs(tmp_path, *runs) -> Derived:
    client = Derived()
    for days, run in enumerate(runs, start=1):
        aggregate.upload(client, test_write.site(tmp_path / run, days=days), run=run)
    return client


class FakeS3:
    def __init__(self, *, fail_on_put=None, after_put=None, objects=()):
        self.objects = {key: (b"old", None, None) for key in objects}
        self.puts, self.buckets = [], set()
        self.fail_on_put, self.after_put, self.fail_listing = fail_on_put, after_put, False

    def put_object(self, *, Bucket, Key, Body, ContentType, CacheControl):
        if len(self.puts) + 1 == self.fail_on_put:
            raise ClientError({"Error": {"Code": "InternalError"}}, "PutObject")
        self.buckets.add(Bucket)
        self.puts.append(Key)
        self.objects[Key] = (Body, ContentType, CacheControl)
        if self.after_put:
            self.after_put(len(self.puts))

    def get_paginator(self, name):
        assert name == "list_objects_v2"
        return self

    def paginate(self, Bucket, Prefix):
        if self.fail_listing:
            raise ClientError({"Error": {"Code": "SlowDown"}}, "ListObjectsV2")
        yield {"Contents": [{"Key": key} for key in sorted(self.objects) if key.startswith(Prefix)]}

    def delete_object(self, *, Bucket, Key):
        del self.objects[Key]

    def get_object(self, *, Bucket, Key):
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        return {"Body": io.BytesIO(self.objects[Key][0])}


def run_files(client, run):
    return sorted(n for b, n in client.store if b == DERIVED_BUCKET and f"runs/{run}/" in n)


def test_every_file_goes_up_before_the_pointer_with_the_right_headers(tmp_path):
    derived = publish_runs(tmp_path, OLD, NEW)
    before = dict(derived.store)
    s3 = FakeS3()

    assert r2.publish(derived, s3, "howlate") == (4, True)

    assert s3.puts[:-1] == run_files(derived, NEW)
    assert s3.puts[-1] == POINTER
    for key in s3.puts[:-1]:
        body, content_type, cache = s3.objects[key]
        assert body == derived.store[(DERIVED_BUCKET, key)]
        assert content_type == "application/json"
        assert cache == "public, max-age=31536000, immutable"
    body, content_type, cache = s3.objects[POINTER]
    assert body == derived.store[(DERIVED_BUCKET, POINTER)]
    assert (content_type, cache) == ("application/json", "public, max-age=60")
    assert s3.buckets == {"howlate"}
    assert derived.store == before


@pytest.mark.parametrize("nth", [1, 3, 4])
def test_a_failed_put_leaves_the_pointer_on_the_previous_run(tmp_path, nth):
    derived = publish_runs(tmp_path, OLD, NEW)
    s3 = FakeS3(fail_on_put=nth, objects=[POINTER])
    with pytest.raises(ClientError):
        r2.publish(derived, s3, "howlate")
    assert POINTER not in s3.puts
    assert s3.objects[POINTER][0] == b"old"


def test_a_run_missing_files_is_not_copied(tmp_path):
    derived = publish_runs(tmp_path, NEW)
    del derived.store[(DERIVED_BUCKET, run_files(derived, NEW)[0])]
    s3 = FakeS3()
    with pytest.raises(RuntimeError, match="lists 3 files but its pointer says 4"):
        r2.publish(derived, s3, "howlate")
    assert s3.puts == []


def test_a_run_that_finishes_mid_copy_with_a_partial_listing_keeps_the_pointer_back(tmp_path):
    # The derived pointer names OLD while NEW is still uploading, so the first
    # read cannot check NEW's file count. NEW's upload then finishes during the
    # copy, and the second read sees a pointer for NEW over a listing of 2 of 4.
    derived = publish_runs(tmp_path, OLD)
    full = publish_runs(tmp_path / "full", NEW)
    names = run_files(full, NEW)
    assert len(names) == 4
    for name in names[:2]:
        derived.store[(DERIVED_BUCKET, name)] = full.store[(DERIVED_BUCKET, name)]

    def upload_finishes(puts):
        if puts == 1:
            for name in names[2:]:
                derived.store[(DERIVED_BUCKET, name)] = full.store[(DERIVED_BUCKET, name)]
            derived.store[(DERIVED_BUCKET, POINTER)] = full.store[(DERIVED_BUCKET, POINTER)]

    s3 = FakeS3(after_put=upload_finishes, objects=[POINTER])
    with pytest.raises(RuntimeError, match="lists 2 files but its pointer says 4"):
        r2.publish(derived, s3, "howlate", run=NEW)
    assert POINTER not in s3.puts
    assert s3.objects[POINTER][0] == b"old"


def test_the_run_r2_readers_were_just_told_about_survives_the_copy_and_the_next_prunes_it(tmp_path):
    a, b, c, d = (f"2026110{day}T130000Z-aaaaaa" for day in (1, 2, 3, 4))
    derived = publish_runs(tmp_path, a, b, c, d)
    a_files = [f"site/runs/{a}/index.json", f"site/runs/{a}/lines/801.json"]
    s3 = FakeS3(objects=[*a_files, POINTER])
    s3.objects[POINTER] = (json.dumps({"run": a, "previous": []}).encode(), None, None)

    assert r2.publish(derived, s3, "howlate") == (4, True)
    assert all(key in s3.objects for key in a_files)  # readers may still hold A's pointer

    assert r2.publish(derived, s3, "howlate") == (4, True)
    assert not any(key in s3.objects for key in a_files)


def test_an_unreadable_r2_pointer_does_not_stop_the_copy(tmp_path, capsys):
    s3 = FakeS3(objects=[POINTER])  # holds b"old", which is not JSON
    assert r2.publish(publish_runs(tmp_path, NEW), s3, "howlate") == (4, True)
    assert "could not read R2 pointer: JSONDecodeError" in capsys.readouterr().out


def test_a_newer_run_published_during_the_copy_keeps_its_pointer(tmp_path):
    derived = publish_runs(tmp_path, OLD)

    def newer_run_lands(puts):
        if puts == 2:
            aggregate.upload(derived, test_write.site(tmp_path / NEW, days=9), run=NEW)

    s3 = FakeS3(after_put=newer_run_lands)
    assert r2.publish(derived, s3, "howlate") == (4, False)
    assert POINTER not in s3.puts


def test_an_older_run_named_by_hand_copies_its_files_and_not_the_pointer(tmp_path):
    derived = publish_runs(tmp_path, OLD, NEW)
    s3 = FakeS3()
    assert r2.publish(derived, s3, "howlate", run=OLD) == (4, False)
    assert s3.puts == run_files(derived, OLD)


def test_pruning_keeps_exactly_the_runs_the_pointer_names(tmp_path):
    runs = [f"2026110{day}T130000Z-aaaaaa" for day in range(1, 6)]
    derived = publish_runs(tmp_path, *runs)
    pointer = r2.read_pointer(derived.bucket(DERIVED_BUCKET))[1]
    assert pointer["previous"] == [runs[3], runs[2]]

    flat, ahead = "site/index.json", "site/runs/20261109T130000Z-zzzzzz/index.json"
    s3 = FakeS3(objects=[f"site/runs/{run}/index.json" for run in runs] + [flat, ahead, POINTER])
    r2.publish(derived, s3, "howlate")

    names = {key.split("/")[2] for key in s3.objects if key.startswith("site/runs/")}
    assert names == {*runs[2:], "20261109T130000Z-zzzzzz"}  # three kept, one ahead of this run
    assert flat not in s3.objects
    assert s3.objects[POINTER][0] == derived.store[(DERIVED_BUCKET, POINTER)]


def test_a_failed_prune_does_not_fail_the_copy(tmp_path, capsys):
    s3 = FakeS3()
    s3.fail_listing = True
    assert r2.publish(publish_runs(tmp_path, NEW), s3, "howlate") == (4, True)
    assert "could not prune old R2 runs: SlowDown during ListObjectsV2" in capsys.readouterr().out


ENV = {"R2_ENDPOINT": "https://acct.r2.cloudflarestorage.com", "R2_ACCESS_KEY_ID": "id-1",
       "R2_SECRET_ACCESS_KEY": "s3cret"}  # fmt: skip


def test_with_no_settings_the_copy_is_skipped_without_touching_either_bucket(capsys):
    assert r2.from_env({}) is None
    assert r2.from_env({"R2_BUCKET": "howlate", "R2_ENDPOINT": " "}) is None
    assert r2.copy_if_configured(None, env={}) is False
    assert "R2 copy skipped" in capsys.readouterr().out


def test_partial_settings_name_what_is_missing_and_never_print_a_value():
    with pytest.raises(ValueError, match="missing R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY") as seen:
        r2.from_env({"R2_ENDPOINT": ENV["R2_ENDPOINT"]})
    assert "acct" not in str(seen.value)
    with pytest.raises(ValueError, match="missing R2_ENDPOINT"):
        r2.from_env({k: v for k, v in ENV.items() if k != "R2_ENDPOINT"})


def test_full_settings_default_the_bucket_and_keep_secrets_out_of_the_repr():
    config = r2.from_env(ENV)
    assert config.bucket == "howlate"
    assert r2.from_env({**ENV, "R2_BUCKET": "other"}).bucket == "other"
    assert "s3cret" not in repr(config) and "id-1" not in repr(config)


def test_an_error_is_described_without_the_endpoint():
    error = ClientError({"Error": {"Code": "AccessDenied"}}, "PutObject")
    assert r2.describe(error) == "AccessDenied during PutObject"


def test_an_unknown_error_is_described_by_its_type_alone():
    # botocore raises ValueError("Invalid endpoint: <url>") for a bad endpoint.
    error = ValueError("Invalid endpoint: https://0123abcd.r2.cloudflarestorage.com")
    assert r2.describe(error) == "ValueError"


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://acct_1.r2.cloudflarestorage.com",
        "https://acct 1.r2.cloudflarestorage.com",
        "http://acct.r2.cloudflarestorage.com",
        "https://acct.r2.cloudflarestorage.com/howlate",
        "https://acct.r2.cloudflarestorage.com?x=1",
        "https://user:pw@acct.r2.cloudflarestorage.com",
        "https://[acct.r2.cloudflarestorage.com",
    ],
)
def test_a_malformed_endpoint_is_rejected_without_echoing_it(endpoint):
    with pytest.raises(ValueError, match="R2_ENDPOINT is not a valid https address") as seen:
        r2.from_env({**ENV, "R2_ENDPOINT": endpoint})
    assert "acct" not in str(seen.value) and "pw" not in str(seen.value)


def test_an_account_endpoint_passes():
    endpoint = f"https://{'0123456789abcdef' * 2}.r2.cloudflarestorage.com"
    assert r2.from_env({**ENV, "R2_ENDPOINT": endpoint}).endpoint == endpoint


def test_the_configured_copy_uses_the_client_it_is_given(tmp_path):
    derived, s3 = publish_runs(tmp_path, NEW), FakeS3()
    assert r2.copy_if_configured(derived, env={**ENV, "R2_BUCKET": "other"}, s3=s3) is True
    assert s3.buckets == {"other"}


def test_the_two_cors_files_say_the_same_thing():
    # r2-cors.json is for the dashboard and r2-cors.wrangler.json for wrangler,
    # which want different shapes. Only a checkout has them; the container job
    # mounts pipeline/tests alone.
    deploy = Path(__file__).resolve().parents[1] / "deploy"
    if not (deploy.parent / "pyproject.toml").is_file():
        pytest.skip("not a pipeline checkout, as in the container job")
    (dashboard,) = json.loads((deploy / "r2-cors.json").read_text())
    (wrangler,) = json.loads((deploy / "r2-cors.wrangler.json").read_text())["rules"]
    assert dashboard["AllowedOrigins"] == wrangler["allowed"]["origins"] == ["*"]
    assert dashboard["AllowedMethods"] == wrangler["allowed"]["methods"] == ["GET", "HEAD"]
    assert dashboard["MaxAgeSeconds"] == wrangler["maxAgeSeconds"] == 3600
    assert "AllowedHeaders" not in dashboard and "headers" not in wrangler["allowed"]
