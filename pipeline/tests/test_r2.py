"""Copying a published run to R2: order, headers, the pointer, pruning, and config.

No network. The derived bucket is test_write's fake and R2 is FakeS3 below, so
a test can see every object written and in what order.
"""

import argparse
import io
import json
import urllib.error
from datetime import date
from pathlib import Path

import pytest
import test_write
from botocore.exceptions import ClientError

from howlate_pipeline import DERIVED_BUCKET, aggregate, r2
from howlate_pipeline import __main__ as cli

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
    with pytest.raises(r2.Notice, match="missing R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY") as seen:
        r2.from_env({"R2_ENDPOINT": ENV["R2_ENDPOINT"]})
    assert "acct" not in str(seen.value)
    with pytest.raises(r2.Notice, match="missing R2_ENDPOINT"):
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
    with pytest.raises(r2.Notice, match="R2_ENDPOINT is not a valid https address") as seen:
        r2.from_env({**ENV, "R2_ENDPOINT": endpoint})
    assert "acct" not in str(seen.value) and "pw" not in str(seen.value)


@pytest.mark.parametrize(
    "value", [" https://host", "https://ho\nst", "https://host\n", "HTTPS://host", "https://host "]
)
def test_the_address_check_looks_at_the_whole_value_not_what_urlsplit_keeps(value):
    assert r2.is_https_address(value) is False


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


PUBLIC = "https://data.howlate.la"
WEB_ENV = {**ENV, "R2_PUBLIC_URL": PUBLIC}


@pytest.mark.parametrize(
    "value", ["1", "true", "TRUE", "yes", " 1 ", "on", "y", "2", "enabled", "ON", "Enabled"]
)
def test_a_required_copy_with_no_settings_fails_naming_the_variable(value):
    # Local runs skip R2. The deployed job must not, or a redeploy that loses
    # the settings leaves the public site stale with a success ping.
    with pytest.raises(r2.Notice, match="R2_REQUIRED") as seen:
        r2.copy_if_configured(None, env={"R2_REQUIRED": value})
    assert "stale" in str(seen.value)
    assert "https://" not in str(seen.value)


@pytest.mark.parametrize(
    "value", ["", " ", "0", "no", "false", "off", "none", "False", "NO", "Off", "NONE", " 0 "]
)
def test_an_unset_or_false_r2_required_keeps_the_skip(value, capsys):
    assert r2.copy_if_configured(None, env={"R2_REQUIRED": value}) is False
    assert "R2 copy skipped" in capsys.readouterr().out


def test_a_half_set_environment_still_names_what_is_missing_when_required():
    with pytest.raises(r2.Notice, match="missing R2_ACCESS_KEY_ID"):
        r2.copy_if_configured(
            None,
            env={
                "R2_REQUIRED": "1",
                "R2_ENDPOINT": ENV["R2_ENDPOINT"],
                "R2_SECRET_ACCESS_KEY": "x",
            },
        )


# The daily job runs at 05:00 Pacific and grades up to two days back, so on a
# healthy day the public last_day is two days before today.
TODAY = date(2026, 11, 9)


class Web:
    """The public address as the probe sees it, with every URL it was asked for."""

    def __init__(self, *, run=NEW, last_day="2026-11-07", pointer=None, status=None):
        self.urls = []
        prefix = f"site/runs/{run}/"
        self.pages = {
            "site/current.json": pointer or (200, json.dumps({"run": run, "prefix": prefix})),
            f"{prefix}status.json": status or (200, json.dumps({"last_day": last_day})),
        }

    def __call__(self, url):
        self.urls.append(url)
        path = url.removeprefix(PUBLIC + "/").split("?")[0]
        status, body = self.pages.get(path, (404, ""))
        return status, body.encode()


def test_the_probe_passes_when_the_public_pointer_names_the_copied_run_and_is_current():
    web = Web()
    r2.probe(PUBLIC, NEW, TODAY, web)
    assert web.urls[0].startswith(f"{PUBLIC}/site/current.json?nocache=")
    assert web.urls[1] == f"{PUBLIC}/site/runs/{NEW}/status.json"


def test_the_probe_passes_when_a_newer_run_was_published_meanwhile():
    r2.probe(PUBLIC, OLD, TODAY, Web(run=NEW))


def test_the_probe_asks_for_the_pointer_with_the_current_time_as_its_query(monkeypatch):
    # The pointer is served with a 60 second cache, so a fixed address could
    # return the previous run's pointer and read as stale.
    monkeypatch.setattr(r2.time, "time", lambda: 1_800_000_000.7)
    web = Web()
    r2.probe(PUBLIC, NEW, TODAY, web)
    assert web.urls[0] == f"{PUBLIC}/site/current.json?nocache=1800000000"


@pytest.mark.parametrize(
    ("web", "message"),
    [
        (Web(pointer=(404, "")), "site/current.json returned 404"),
        (Web(pointer=(200, "<html>")), "site/current.json is not JSON"),
        (Web(pointer=(200, "[]")), "site/current.json is not a JSON object"),
        (Web(pointer=(200, '{"run": "x"}')), "site/current.json has no usable run and prefix"),
        (Web(pointer=(200, '{"run": "a", "prefix": "../x/"}')), "no usable run and prefix"),
        (Web(run=OLD), f"names {OLD}, older than the copied {NEW}"),
        (Web(status=(500, "")), "status.json returned 500"),
        (Web(status=(200, "nope")), "status.json is not JSON"),
        (Web(status=(200, "{}")), "status.json has no valid last_day"),
        (Web(last_day="soon"), "status.json has no valid last_day"),
        (Web(last_day=""), "status.json has no valid last_day"),
        (Web(status=(200, '{"last_day": 20261107}')), "status.json has no valid last_day"),
        (Web(last_day="2026-11-04"), "last_day 2026-11-04 is 5 days before today, more than 4"),
    ],
)
def test_the_probe_fails_and_says_which_check_failed(web, message):
    with pytest.raises(r2.Notice, match=message) as seen:
        r2.probe(PUBLIC, NEW, TODAY, web)
    assert "data.howlate.la" not in str(seen.value)


@pytest.mark.parametrize("last_day", ["2026-11-07", "2026-11-05"])
def test_the_probe_allows_a_last_day_two_and_four_days_before_today(last_day):
    r2.probe(PUBLIC, NEW, TODAY, Web(last_day=last_day))


def test_the_freshness_check_compares_with_today_not_with_the_site_it_just_built():
    # The old check compared the public file with the site this job had just
    # built and uploaded, so a job that graded nothing for a week still passed.
    stale = Web(last_day="2026-11-01")
    with pytest.raises(r2.Notice, match="last_day 2026-11-01 is 8 days before today"):
        r2.probe(PUBLIC, NEW, TODAY, stale)
    r2.probe(PUBLIC, NEW, date(2026, 11, 3), stale)


def test_a_failed_fetch_is_reported_by_its_type_alone():
    def down(url):
        raise urllib.error.URLError("https://data.howlate.la refused")

    with pytest.raises(r2.Notice, match=r"could not fetch site/current.json \(URLError\)") as seen:
        r2.probe(PUBLIC, NEW, TODAY, down)
    assert "howlate.la" not in str(seen.value)


class Reply:
    status = 200

    def read(self):
        return b"{}"

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_the_real_fetch_retries_once_and_then_gives_up(monkeypatch):
    monkeypatch.setattr(r2.time, "sleep", lambda seconds: None)
    calls = []

    def flaky(request, timeout):
        calls.append(timeout)
        if len(calls) == 1:
            raise urllib.error.URLError("reset")
        return Reply()

    monkeypatch.setattr(r2.urllib.request, "urlopen", flaky)
    assert r2.fetch_public(PUBLIC + "/x") == (200, b"{}")
    assert len(calls) == 2 and calls[0] <= 10

    calls.clear()
    monkeypatch.setattr(
        r2.urllib.request, "urlopen", lambda request, timeout: calls.append(1) or 1 / 0
    )
    with pytest.raises(ZeroDivisionError):
        r2.fetch_public(PUBLIC + "/x")
    assert len(calls) == 2


def local_site(tmp_path) -> Path:
    site = tmp_path / "local"
    site.mkdir()
    return site


def copy(derived, tmp_path, *, env=WEB_ENV, s3=None, fetch=None, **kwargs):
    return r2.copy_if_configured(
        derived,
        env=env,
        s3=s3 or FakeS3(),
        site_dir=local_site(tmp_path),
        fetch=fetch or Web(),
        today=TODAY,
        **kwargs,
    )


def test_the_copy_checks_the_public_address_after_the_pointer_moves(tmp_path):
    derived, web = publish_runs(tmp_path, OLD, NEW), Web()
    assert copy(derived, tmp_path, fetch=web)
    assert len(web.urls) == 2


def test_a_stale_public_site_fails_the_copy(tmp_path):
    derived, web = publish_runs(tmp_path, OLD, NEW), Web(last_day="2026-11-01")
    with pytest.raises(r2.Notice, match="last_day"):
        copy(derived, tmp_path, fetch=web)


def test_the_copy_judges_the_public_site_by_today_in_los_angeles(tmp_path, monkeypatch):
    # The default `today` is the Pacific calendar date, not the machine's.
    derived, web = publish_runs(tmp_path, NEW), Web(last_day="2026-11-07")
    clock = []

    class Clock(r2.datetime):
        @classmethod
        def now(cls, tz=None):
            clock.append(tz)
            return cls(2026, 11, 9, 23, 30, tzinfo=tz)

    monkeypatch.setattr(r2, "datetime", Clock)
    assert r2.copy_if_configured(
        derived, env=WEB_ENV, s3=FakeS3(), site_dir=local_site(tmp_path), fetch=web
    )
    assert [str(tz) for tz in clock] == ["America/Los_Angeles"]


def test_the_probe_does_not_depend_on_the_local_site_file(tmp_path):
    # The check compares with the calendar, so an unreadable or missing local
    # status.json cannot raise anything.
    derived, web = publish_runs(tmp_path, NEW), Web()
    assert r2.copy_if_configured(
        derived,
        env=WEB_ENV,
        s3=FakeS3(),
        site_dir=tmp_path / "does-not-exist",
        fetch=web,
        today=TODAY,
    )
    assert len(web.urls) == 2


def test_with_no_public_address_the_probe_is_skipped_and_logged(tmp_path, capsys):
    derived = publish_runs(tmp_path, NEW)
    assert copy(derived, tmp_path, env=ENV)
    assert "R2 freshness check skipped: R2_PUBLIC_URL not set" in capsys.readouterr().out


def test_a_required_copy_with_no_public_address_fails_before_copying(tmp_path):
    derived, s3 = publish_runs(tmp_path, NEW), FakeS3()
    with pytest.raises(r2.Notice, match="R2_REQUIRED is set but R2_PUBLIC_URL is not"):
        copy(derived, tmp_path, env={**ENV, "R2_REQUIRED": "1"}, s3=s3)
    assert s3.puts == []


@pytest.mark.parametrize("url", ["", "http://data.howlate.la", f"{PUBLIC}/", f"{PUBLIC}:443"])
def test_a_missing_or_bad_public_address_is_a_notice_even_when_the_pointer_would_stay(
    tmp_path, url
):
    # A newer run lands mid-copy, so R2's pointer would be left alone and the
    # old guard, which ran after the pointer moved, never looked at the address.
    derived = publish_runs(tmp_path, OLD)

    def newer_run_lands(puts):
        if puts == 2:
            aggregate.upload(derived, test_write.site(tmp_path / NEW, days=9), run=NEW)

    s3 = FakeS3(after_put=newer_run_lands)
    with pytest.raises(r2.Notice, match="R2_PUBLIC_URL") as seen:
        copy(derived, tmp_path, env={**ENV, "R2_REQUIRED": "1", "R2_PUBLIC_URL": url}, s3=s3)
    assert s3.puts == []
    assert "howlate.la" not in str(seen.value)


def test_a_required_copy_with_no_site_dir_does_not_need_the_public_address(tmp_path):
    derived, s3, web = publish_runs(tmp_path, NEW), FakeS3(), Web()
    assert r2.copy_if_configured(
        derived, env={**ENV, "R2_REQUIRED": "1"}, s3=s3, fetch=web, today=TODAY
    )
    assert POINTER in s3.puts
    assert web.urls == []


def test_a_bad_public_address_does_not_stop_a_copy_that_has_no_site_dir(tmp_path):
    derived, s3 = publish_runs(tmp_path, NEW), FakeS3()
    env = {**ENV, "R2_REQUIRED": "1", "R2_PUBLIC_URL": "not a url"}
    assert r2.copy_if_configured(derived, env=env, s3=s3)
    assert POINTER in s3.puts


def publish_cli(monkeypatch, derived, s3, env):
    for name in (*r2.REQUIRED, "R2_REQUIRED", "R2_PUBLIC_URL", "R2_BUCKET"):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(cli, "Bucket", lambda: lambda: derived)
    monkeypatch.setattr(r2, "make_client", lambda config: s3)
    return cli.run_publish_r2(argparse.Namespace(site_run=None))


@pytest.mark.parametrize("extra", [{}, {"R2_PUBLIC_URL": "http://bad host"}])
def test_publish_r2_neither_probes_nor_needs_the_public_address(tmp_path, monkeypatch, extra):
    derived, s3 = publish_runs(tmp_path, NEW), FakeS3()
    monkeypatch.setattr(
        r2, "fetch_public", lambda url: pytest.fail("publish-r2 must not fetch the public site")
    )
    assert publish_cli(monkeypatch, derived, s3, {**ENV, "R2_REQUIRED": "1", **extra}) == 0
    assert POINTER in s3.puts


@pytest.mark.parametrize(
    ("env", "message"),
    [
        ({"R2_REQUIRED": "1"}, "R2_REQUIRED is set but the R2 settings are not"),
        ({"R2_ENDPOINT": ENV["R2_ENDPOINT"]}, "R2 is partly configured; missing R2_ACCESS_KEY_ID"),
        ({**ENV, "R2_ENDPOINT": "http://x"}, "R2_ENDPOINT is not a valid https address"),
    ],
)
def test_publish_r2_turns_a_notice_into_one_line_and_exit_1(tmp_path, monkeypatch, env, message):
    derived = publish_runs(tmp_path, NEW)
    with pytest.raises(SystemExit) as seen:
        publish_cli(monkeypatch, derived, FakeS3(), env)
    assert message in str(seen.value.code)
    assert "\n" not in str(seen.value.code)
    assert seen.value.code != 0


def test_publish_r2_with_no_settings_still_says_nothing_was_copied(tmp_path, monkeypatch):
    with pytest.raises(SystemExit, match="nothing copied"):
        publish_cli(monkeypatch, publish_runs(tmp_path, NEW), FakeS3(), {})


@pytest.mark.parametrize(
    "url", ["http://data.howlate.la", f"{PUBLIC}/", f"{PUBLIC}/site", "https://a b.la"]
)
def test_a_malformed_public_address_is_rejected_without_echoing_it(url):
    with pytest.raises(r2.Notice, match="R2_PUBLIC_URL is not a valid https address") as seen:
        r2.public_url_from_env({"R2_PUBLIC_URL": url})
    assert "howlate" not in str(seen.value)


def test_the_probe_judges_the_run_that_was_copied_not_the_one_named_later(tmp_path):
    # A hand-run copy of OLD while NEW is current: R2's pointer stays on NEW, so
    # the copy says it left the pointer alone and nothing is probed.
    derived, web = publish_runs(tmp_path, OLD, NEW), Web()
    assert copy(derived, tmp_path, run=OLD, fetch=web)
    assert web.urls == []


def test_a_newer_run_landing_during_the_copy_is_not_a_failure(tmp_path, capsys):
    # The second writer: R2's pointer is left alone, the public pointer is
    # still the previous run, and the probe must not call that stale.
    derived = publish_runs(tmp_path, OLD)

    def newer_run_lands(puts):
        if puts == 2:
            aggregate.upload(derived, test_write.site(tmp_path / NEW, days=9), run=NEW)

    web = Web(run=OLD)
    s3 = FakeS3(after_put=newer_run_lands)
    assert copy(derived, tmp_path, s3=s3, fetch=web)
    assert web.urls == []
    assert "R2 freshness check skipped: R2's pointer was left alone" in capsys.readouterr().out


@pytest.mark.parametrize("value", ["on", "y", "2", "enabled", "1", "true", "Anything"])
def test_r2_required_is_set_by_any_value_that_is_not_an_explicit_no(value):
    assert r2.is_required({"R2_REQUIRED": value}) is True


@pytest.mark.parametrize("value", ["0", "false", "no", "off", "none", "FALSE", "  "])
def test_r2_required_is_unset_by_an_explicit_no(value):
    assert r2.is_required({"R2_REQUIRED": value}) is False


def test_r2_required_is_unset_when_the_variable_is_missing_or_empty():
    assert r2.is_required({}) is False
    assert r2.is_required({"R2_REQUIRED": ""}) is False
