"""The daily job: catch up, rebuild the site from every finished day, and report.

Grading, fetching and building are replaced by fakes, so these tests check the
job's decisions rather than repeat the grading tests. A few name the part they
leave real, where the decision under test sits across that part's boundary.
"""

import argparse

import pytest
import test_write
from botocore.exceptions import ClientError

from howlate_pipeline import DERIVED_BUCKET, aggregate, arrivals, backfill, labels, r2
from howlate_pipeline import __main__ as cli


class FakeBlob:
    def __init__(self, done: set, name: str):
        self.done, self.name = done, name

    def exists(self) -> bool:
        return any(day in self.name for day in self.done)


class FakeClient:
    def __init__(self, done):
        self.done = done

    def bucket(self, name):
        return self

    def blob(self, name):
        return FakeBlob(self.done, name)


class Run:
    """One daily run with every outside effect recorded."""

    def __init__(
        self,
        monkeypatch,
        tmp_path,
        *,
        done=(),
        codes=None,
        raises=None,
        site=None,
        fetched=1,
        real=(),
        r2_error=None,
    ):
        # `real` names what is left unfaked: "grade" or "build". The R2 copy is
        # replaced by a recorder, raising `r2_error` when one is given; with
        # `real` holding "r2" it runs for real, with no R2 settings.
        self.graded, self.pings, self.built, self.fetched, self.published = [], [], [], [], []
        self.copied, self.summaries, self.copy_kwargs = [], [], []
        for name in (*r2.REQUIRED, "R2_REQUIRED", "R2_PUBLIC_URL"):
            monkeypatch.delenv(name, raising=False)
        done = {f"{d[:4]}-{d[4:6]}-{d[6:]}" for d in done}
        monkeypatch.setattr(cli, "yesterday", lambda: "20261107")
        monkeypatch.setattr(cli, "Bucket", lambda: lambda: FakeClient(done))

        def ping(ok, summary):
            self.pings.append(ok)
            self.summaries.append(summary)

        monkeypatch.setattr(cli, "heartbeat", ping)

        def copy(client, run=None, **kwargs):
            self.copied.append(run)
            self.copy_kwargs.append(kwargs)
            if r2_error:
                raise r2_error
            return True

        if "r2" not in real:
            monkeypatch.setattr(cli.r2, "copy_if_configured", copy)

        def fetch(client, dest):
            self.fetched.append(dest)
            return fetched

        monkeypatch.setattr(cli.aggregate, "fetch_arrivals", fetch)

        def grade(bucket, day, **kwargs):
            self.graded.append(day)
            if raises and day in raises:
                raise raises[day]
            return (codes or {}).get(day, 0)

        def build(bucket, graded, **kwargs):
            if site:
                raise site
            self.built.append(graded)
            self.published.append(kwargs.get("upload", True))
            return 0

        if "grade" not in real:
            monkeypatch.setattr(cli, "grade_day", grade)
        if "build" not in real:
            monkeypatch.setattr(cli, "build_site", build)
        self.args = argparse.Namespace(catch_up=7, cache=tmp_path / "cache", out=tmp_path / "out")

    def __call__(self):
        return cli.run_daily(self.args)


def test_it_looks_back_seven_days_ending_at_the_last_complete_one(monkeypatch, tmp_path):
    run = Run(monkeypatch, tmp_path)
    assert run() == 0
    assert run.graded == [f"202611{day:02d}" for day in range(1, 8)]


def test_days_already_graded_are_skipped(monkeypatch, tmp_path):
    run = Run(monkeypatch, tmp_path, done=["20261101", "20261102", "20261103", "20261104",
                                           "20261105", "20261106"])  # fmt: skip
    run()
    assert run.graded == ["20261107"]


def test_a_clean_run_rebuilds_the_site_and_reports_ok(monkeypatch, tmp_path):
    run = Run(monkeypatch, tmp_path)
    assert run() == 0
    assert run.built == [tmp_path / "cache" / "graded" / arrivals.VERSION]
    assert run.pings == [True]


def test_a_clean_run_summarises_every_graded_day_and_publishes(monkeypatch, tmp_path):
    # Issue #17: a run updates the site files. On Cloud Run the disk starts
    # empty, so the summary must read days fetched from the bucket.
    run = Run(monkeypatch, tmp_path)
    run()
    assert run.fetched == run.built
    assert run.published == [True]


def test_the_site_is_copied_to_r2_after_it_is_published_and_the_run_reports_ok(
    monkeypatch, tmp_path
):
    run = Run(monkeypatch, tmp_path)
    assert run() == 0
    assert run.copied == [None]  # the run the published pointer names
    assert run.pings == [True]


def test_a_failed_r2_copy_exits_nonzero_and_pings_failure_without_the_endpoint(
    monkeypatch, tmp_path
):
    # The graded days and the GCS site are saved by then. A stale public site
    # must still not go unnoticed.
    error = ClientError({"Error": {"Code": "AccessDenied"}}, "PutObject")
    run = Run(monkeypatch, tmp_path, r2_error=error)
    assert run() == 1
    assert len(run.built) == 1
    assert run.pings == [False]
    assert "R2 copy failed: AccessDenied during PutObject" in run.summaries[0]


def test_a_failed_r2_copy_does_not_hide_a_failed_check(monkeypatch, tmp_path):
    run = Run(monkeypatch, tmp_path, codes={"20261107": 2}, r2_error=RuntimeError("no"))
    assert run() == 2
    assert run.pings == [False]
    assert "R2 copy failed" in run.summaries[0]


def test_a_site_that_fails_to_publish_is_not_copied_to_r2(monkeypatch, tmp_path):
    run = Run(monkeypatch, tmp_path, site=RuntimeError("bucket unreachable"))
    with pytest.raises(RuntimeError):
        run()
    assert run.copied == []


def test_the_copy_is_given_the_site_the_run_just_built_to_check_against(monkeypatch, tmp_path):
    run = Run(monkeypatch, tmp_path)
    run()
    assert run.copy_kwargs == [{"site_dir": tmp_path / "out" / "site"}]


def test_a_required_r2_with_no_settings_fails_the_run_and_the_ping_names_the_variable(
    monkeypatch, tmp_path
):
    # The deploy workflow only updates the image, so a redeploy that loses the
    # R2 settings must not read as a clean skip.
    run = Run(monkeypatch, tmp_path, real=("r2",))
    monkeypatch.setenv("R2_REQUIRED", "1")
    assert run() == 1
    assert run.pings == [False]
    assert "R2_REQUIRED" in run.summaries[0]
    assert "public site would go stale" in run.summaries[0]


def test_a_failed_public_check_fails_the_run_with_its_own_message(monkeypatch, tmp_path):
    error = r2.Notice("R2 public check failed: site/current.json returned 404")
    run = Run(monkeypatch, tmp_path, r2_error=error)
    assert run() == 1
    assert run.pings == [False]
    assert "R2 public check failed: site/current.json returned 404" in run.summaries[0]
    # The copy worked, so the ping must not say the site is in Cloud Storage only.
    assert "Cloud Storage only" not in run.summaries[0]


def test_with_no_r2_settings_the_daily_run_is_as_it_was(monkeypatch, tmp_path, capsys):
    run = Run(monkeypatch, tmp_path, real=("r2",))
    assert run() == 0
    assert run.pings == [True]
    assert "R2 copy skipped" in capsys.readouterr().out


def test_a_day_that_errors_still_rebuilds_the_site_and_raises_the_alarm(monkeypatch, tmp_path):
    # A day with no raw files is how a collector outage shows up here. It must
    # not hold back the days after it.
    run = Run(monkeypatch, tmp_path, raises={"20261101": SystemExit("no raw files")})
    assert run() == 1
    assert run.graded == [f"202611{day:02d}" for day in range(1, 8)]
    assert len(run.built) == 1
    assert run.pings == [False]


def test_with_no_finished_day_the_site_is_left_and_the_days_reported(monkeypatch, tmp_path):
    every = {f"202611{day:02d}": SystemExit("no raw files") for day in range(1, 8)}
    run = Run(monkeypatch, tmp_path, raises=every, fetched=0)
    assert run() == 1
    assert run.built == []
    assert run.pings == [False]


def test_failed_checks_still_rebuild_the_site_but_raise_the_alarm(monkeypatch, tmp_path):
    run = Run(monkeypatch, tmp_path, codes={"20261107": 2})
    assert run() == 2
    assert len(run.built) == 1
    assert run.pings == [False]


def test_a_crash_while_building_the_site_raises_the_alarm_and_the_error(monkeypatch, tmp_path):
    run = Run(monkeypatch, tmp_path, site=RuntimeError("bucket unreachable"))
    with pytest.raises(RuntimeError):
        run()
    assert run.pings == [False]


def test_a_day_with_no_raw_files_raises_the_alarm_and_names_the_day(monkeypatch, tmp_path, capsys):
    # Issue #98: the other tests raise SystemExit from a fake grade. This one
    # lets grade_day raise it, so a reworded or removed exit in grade_day, or a
    # run_daily that stopped catching it, fails here.
    done = [f"202611{day:02d}" for day in range(1, 7)]
    run = Run(monkeypatch, tmp_path, done=done, real=("grade",))
    monkeypatch.setattr(cli.gtfs, "prepare", lambda client, day, cache: {})
    monkeypatch.setattr(cli.arrivals, "fetch_raw", lambda client, day, cache: [])
    assert run() == 1
    assert run.pings == [False]
    # The heartbeat summary only counts days. The day is named in the log.
    log = capsys.readouterr().out
    assert "20261107 failed: SystemExit('no raw files found for 20261107')" in log
    assert "errors: 20261107" in log


def test_the_fail_ping_names_each_failed_day_and_the_first_line_of_its_error(monkeypatch, tmp_path):
    # Issue #100: the summary only counted days, so the person reading the
    # healthchecks.io alert had to open the Cloud Run log to find the day.
    raises = {
        "20261103": SystemExit("no raw files found for 20261103"),
        "20261105": ValueError("bad join\nTraceback-like second line"),
    }
    run = Run(monkeypatch, tmp_path, raises=raises)
    assert run() == 1
    body = run.summaries[0]
    assert "errors 2" in body
    assert "20261103 failed: SystemExit: no raw files found for 20261103" in body
    assert "20261105 failed: ValueError: bad join" in body
    assert "second line" not in body


LEAKY = (
    "403 GET https://storage.googleapis.com/b/howlate-raw/o?x=1: sa-job@howlate-la.iam."
    "gserviceaccount.com does not have access to gs://howlate-raw/vehicle_positions/dt=2026-11-03/a"
)
SECRETS = ("https://", "storage.googleapis.com", "gs://", "howlate-raw", "gserviceaccount", "@")


def test_the_fail_ping_replaces_urls_gs_paths_and_emails_in_an_error(monkeypatch, tmp_path):
    # healthchecks.io is a third party, and a Google API error names the service
    # account and the bucket path.
    run = Run(monkeypatch, tmp_path, raises={"20261103": ValueError(LEAKY)})
    assert run() == 1
    body = run.summaries[0]
    assert (
        "20261103 failed: ValueError: 403 GET <url>: <email> does not have access to <gs-path>"
        in body
    )
    assert not any(secret in body for secret in SECRETS)


def test_the_crash_ping_redacts_the_error_too(monkeypatch, tmp_path):
    run = Run(monkeypatch, tmp_path, site=RuntimeError(LEAKY))
    with pytest.raises(RuntimeError):
        run()
    assert "daily run crashed: RuntimeError('403 GET <url>:" in run.summaries[0]
    assert not any(secret in run.summaries[0] for secret in SECRETS)


def test_the_fail_ping_stays_under_1000_characters_with_many_failures(monkeypatch, tmp_path):
    days = backfill.days_between("20260909", "20261107")
    raises = {day: ValueError(f"{'x' * 60}\nsecond line") for day in days}
    run = Run(monkeypatch, tmp_path, raises=raises, fetched=1)
    run.args.catch_up = len(days)
    assert run() == 1
    body = run.summaries[0]
    assert len(body) < 1000
    assert "errors 60" in body  # the counts come first, so truncation never drops them
    assert f"{days[0]} failed: ValueError: xxx" in body
    shown = body.count(" failed: ValueError")
    assert body.endswith(f"and {len(days) - shown} more days")


def test_seven_failed_days_with_long_first_lines_say_how_many_were_left_out(monkeypatch, tmp_path):
    days = backfill.days_between("20261101", "20261107")
    raises = {day: ValueError("y" * 400) for day in days}
    run = Run(monkeypatch, tmp_path, raises=raises)
    assert run() == 1
    body = run.summaries[0]
    lines = body.splitlines()
    assert len(body) < 1000
    assert all(len(line) <= 160 for line in lines[1:])
    named = [line for line in lines if " failed: ValueError: y" in line]
    assert all(line.endswith("...") for line in named)
    assert 0 < len(named) < 7
    assert lines[-1] == f"and {7 - len(named)} more days"


def test_a_day_that_only_failed_its_checks_is_named(monkeypatch, tmp_path):
    run = Run(monkeypatch, tmp_path, codes={"20261105": 2})
    assert run() == 2
    assert "20261105 failed its checks" in run.summaries[0]
    assert "20261104" not in run.summaries[0]


def test_a_day_whose_cleanup_failed_is_named(monkeypatch, tmp_path):
    def cleanup(cache, day):
        if day == "20261106":
            raise OSError("disk")

    monkeypatch.setattr(cli.backfill, "prune_cache", cleanup)
    run = Run(monkeypatch, tmp_path)
    assert run() == 1
    assert "20261106 cleanup failed" in run.summaries[0]


def test_an_error_that_starts_with_a_newline_keeps_its_text(monkeypatch, tmp_path):
    run = Run(monkeypatch, tmp_path, raises={"20261103": ValueError("\n\n  real cause\nmore")})
    assert run() == 1
    assert "20261103 failed: ValueError: real cause" in run.summaries[0]
    assert "more" not in run.summaries[0]


RESULT = {"skipped": [], "passed": [], "checks_failed": [], "errors": [], "cleanup_failed": []}


def test_a_day_named_with_its_error_is_not_named_again():
    result = {**RESULT, "errors": ["20261103"], "cleanup_failed": ["20261103", "20261104"]}
    body = cli.ping_body("head", {"20261103": ValueError("boom")}, result)
    assert body.count("20261103") == 1
    assert body.splitlines() == [
        "head",
        "20261103 failed: ValueError: boom",
        "20261104 cleanup failed",
    ]


def test_a_day_in_two_buckets_without_an_error_text_is_named_once_with_both():
    result = {**RESULT, "checks_failed": ["20261103"], "cleanup_failed": ["20261103"]}
    body = cli.ping_body("head", {}, result)
    assert body.splitlines() == ["head", "20261103 failed its checks and cleanup failed"]


def test_one_day_left_out_says_day_not_days():
    result = {**RESULT, "checks_failed": ["20261101", "20261102"]}
    body = cli.ping_body("h", {}, result, limit=50)
    assert body == "h\n20261101 failed its checks\nand 1 more day"


def test_a_ping_with_no_failed_days_is_just_the_head():
    assert cli.ping_body("passed 7", {}, RESULT) == "passed 7"


@pytest.mark.parametrize(
    "text",
    [
        "see HTTPS://Example.com/a now",
        "see Https://example.com/a?x=1 now",
        "GS://bucket/key denied",
        "Gs://Bucket/key/dt=2026-11-03/a denied",
        "s3://bucket/key denied",
        "S3://Bucket/key denied",
    ],
)
def test_redaction_covers_uppercase_schemes_and_s3_paths(text):
    out = cli.redact(text)
    assert "ample" not in out and "bucket" not in out.lower()
    assert "://" not in out


def test_redaction_uses_the_same_placeholders_for_every_case():
    assert cli.redact("HTTPS://Example.com/a") == "<url>"
    assert cli.redact("GS://bucket/key") == "<gs-path>"
    assert cli.redact("s3://bucket/key") == "<s3-path>"
    assert cli.redact("S3://bucket/key.") == "<s3-path>."


@pytest.mark.parametrize(
    "text",
    [
        "https://example.com/a",
        "no raw files found for 20261103",
        "connection to example.com refused",
        "the s3 bucket is gs-like and http is a protocol",
        "",
    ],
)
def test_redaction_leaves_ordinary_text_alone_or_redacts_only_the_address(text):
    expected = {"https://example.com/a": "<url>"}.get(text, text)
    assert cli.redact(text) == expected


def test_a_config_error_reaches_the_ping_with_its_reason(monkeypatch, tmp_path):
    # from_env's messages name variables and nothing else, so the ping may show
    # them. As a ValueError the ping said only "ValueError".
    run = Run(monkeypatch, tmp_path, real=("r2",))
    monkeypatch.setenv("R2_ENDPOINT", "https://acct.r2.cloudflarestorage.com")
    assert run() == 1
    assert run.pings == [False]
    summary = run.summaries[0]
    assert "R2 is partly configured; missing R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY" in summary
    assert "ValueError" not in summary


def test_an_invalid_endpoint_reaches_the_ping_without_the_endpoint(monkeypatch, tmp_path):
    run = Run(monkeypatch, tmp_path, real=("r2",))
    for name, value in {**r2_env(), "R2_ENDPOINT": "http://acct.example"}.items():
        monkeypatch.setenv(name, value)
    assert run() == 1
    assert "R2_ENDPOINT is not a valid https address" in run.summaries[0]
    assert "acct" not in run.summaries[0]


def r2_env():
    return {
        "R2_ENDPOINT": "https://acct.r2.cloudflarestorage.com",
        "R2_ACCESS_KEY_ID": "id-1",
        "R2_SECRET_ACCESS_KEY": "s3cret",
    }


def test_a_failed_day_is_named_when_the_r2_copy_fails_too(monkeypatch, tmp_path):
    run = Run(
        monkeypatch,
        tmp_path,
        raises={"20261103": SystemExit("no raw files")},
        r2_error=RuntimeError("no"),
    )
    assert run() == 1
    assert "R2 copy failed" in run.summaries[0]
    assert "20261103 failed: SystemExit: no raw files" in run.summaries[0]


class StoredBlob(test_write.FakeBlob):
    def exists(self) -> bool:
        return (self.bucket_name, self.name) in self.store


class StoredBucket(test_write.FakeBucket):
    def blob(self, name):
        return StoredBlob(self.name, name, self.store)


class Derived(test_write.FakeClient):
    """test_write's bucket, with the exists() that the done rule asks for."""

    def bucket(self, name):
        return StoredBucket(name, self.store)


def crash_in_grading(monkeypatch, run):
    # Not an Exception: backfill.run catches those per day and the run goes on.
    monkeypatch.setattr(cli, "grade_day", lambda *args, **kwargs: raise_(KeyboardInterrupt()))


def crash_in_the_fetch(monkeypatch, run):
    monkeypatch.setattr(aggregate, "fetch_arrivals", lambda *args: raise_(ConnectionError("fetch")))


def crash_in_the_labels(monkeypatch, run):
    # build_site is real here, so the crash lands after the days are loaded
    # and before anything is uploaded.
    monkeypatch.setattr(aggregate, "load", lambda con, directory: ("2026-11-01", "2026-11-07", 7))
    monkeypatch.setattr(cli.gtfs, "prepare", lambda client, day, cache: {})
    monkeypatch.setattr(labels, "load", lambda con, directories: raise_(OSError("labels")))


def raise_(error):
    raise error


@pytest.mark.parametrize(
    ("crash", "error"),
    [
        (crash_in_grading, KeyboardInterrupt),
        (crash_in_the_fetch, ConnectionError),
        (crash_in_the_labels, OSError),
    ],
    ids=["grading", "fetch", "labels"],
)
def test_a_crash_before_the_upload_leaves_the_published_run_alone(
    monkeypatch, tmp_path, crash, error
):
    # Issue #98: the site must keep serving the last complete run, and the
    # alarm must still go off, wherever the job dies before it uploads.
    client = Derived([])
    test_write.publish(client, test_write.site(tmp_path / "seed"), run="20261106T130000Z")

    def site_objects():
        return {key: data for key, data in client.store.items() if key[1].startswith("site/")}

    before = site_objects()
    assert (DERIVED_BUCKET, "site/current.json") in before

    run = Run(monkeypatch, tmp_path, real=("build",))
    monkeypatch.setattr(cli, "Bucket", lambda: lambda: client)
    crash(monkeypatch, run)
    with pytest.raises(error):
        run()
    assert run.pings == [False]
    assert site_objects() == before


class Opened:
    def __init__(self):
        self.urls = []

    def __call__(self, request, timeout):
        self.urls.append(request.full_url)
        return self

    def close(self):
        pass


def test_no_heartbeat_url_means_no_ping(monkeypatch):
    opened = Opened()
    monkeypatch.delenv("HOWLATE_HEARTBEAT_URL", raising=False)
    monkeypatch.setattr(cli.urllib.request, "urlopen", opened)
    cli.heartbeat(True, "fine")
    assert opened.urls == []


def test_heartbeat_pings_the_url_or_its_fail_endpoint(monkeypatch):
    opened = Opened()
    monkeypatch.setenv("HOWLATE_HEARTBEAT_URL", "https://hc-ping.com/abc")
    monkeypatch.setattr(cli.urllib.request, "urlopen", opened)
    cli.heartbeat(True, "fine")
    cli.heartbeat(False, "broken")
    assert opened.urls == ["https://hc-ping.com/abc", "https://hc-ping.com/abc/fail"]


def test_a_failed_ping_does_not_fail_the_run(monkeypatch):
    def unreachable(request, timeout):
        raise OSError("network down")

    monkeypatch.setenv("HOWLATE_HEARTBEAT_URL", "https://hc-ping.com/abc")
    monkeypatch.setattr(cli.urllib.request, "urlopen", unreachable)
    cli.heartbeat(True, "fine")


def test_a_secret_saved_with_a_newline_still_reaches_fail(monkeypatch):
    opened = Opened()
    monkeypatch.setenv("HOWLATE_HEARTBEAT_URL", "https://hc-ping.com/abc\n")
    monkeypatch.setattr(cli.urllib.request, "urlopen", opened)
    cli.heartbeat(False, "broken")
    assert opened.urls == ["https://hc-ping.com/abc/fail"]


def test_a_bad_url_is_ignored_without_printing_the_secret(monkeypatch, capsys):
    monkeypatch.setenv("HOWLATE_HEARTBEAT_URL", "hc-ping.com/secret-uuid")
    cli.heartbeat(False, "broken")
    printed = capsys.readouterr().out
    assert "heartbeat failed: ValueError" in printed
    assert "secret-uuid" not in printed


def test_duckdb_takes_its_memory_and_spill_settings_from_the_job(monkeypatch, tmp_path):
    monkeypatch.setenv("HOWLATE_DUCKDB_MEMORY_LIMIT", "1GB")
    monkeypatch.setenv("HOWLATE_DUCKDB_TEMP_DIRECTORY", str(tmp_path / "spill"))
    con = arrivals.connect()
    limit, spill = con.sql(
        "SELECT current_setting('memory_limit'), current_setting('temp_directory')"
    ).fetchall()[0]
    assert limit in ("1.0 GiB", "953.6 MiB", "1.0 GB", "1000.0 MB")
    assert spill == str(tmp_path / "spill")


class Listed:
    def __init__(self, name):
        self.name = name

    def download_to_filename(self, target):
        target.write_text(self.name)


class Listing:
    def __init__(self, names):
        self.names = names

    def list_blobs(self, bucket, prefix):
        return [Listed(name) for name in self.names if name.startswith(prefix)]


def test_only_days_with_a_report_are_summarised(tmp_path):
    # 2026-11-02's upload died after its table and before its report.
    client = Listing([
        "reports/v2/service_date=2026-11-01/report.json",
        "arrivals/v2/service_date=2026-11-01/part-0.parquet",
        "arrivals/v2/service_date=2026-11-02/part-0.parquet",
    ])  # fmt: skip
    dest = tmp_path / "graded"
    assert cli.aggregate.fetch_arrivals(client, dest) == 1
    assert [p.parent.name for p in dest.rglob("*.parquet")] == ["service_date=2026-11-01"]


def test_a_run_logs_the_commit_it_was_built_from(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("HOWLATE_COMMIT", "545ec6d1a2b3")
    Run(monkeypatch, tmp_path)()
    assert "howlate-pipeline at commit 545ec6d1a2b3" in capsys.readouterr().out
