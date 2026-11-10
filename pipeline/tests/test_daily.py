"""The daily job: catch up, rebuild the site from every finished day, and report.

Grading, fetching and building are replaced by fakes, so these tests check the
job's decisions rather than repeat the grading tests.
"""

import argparse

import pytest

from howlate_pipeline import __main__ as cli
from howlate_pipeline import arrivals


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
        self, monkeypatch, tmp_path, *, done=(), codes=None, raises=None, site=None, fetched=1
    ):
        self.graded, self.pings, self.built, self.fetched, self.published = [], [], [], [], []
        done = {f"{d[:4]}-{d[4:6]}-{d[6:]}" for d in done}
        monkeypatch.setattr(cli, "yesterday", lambda: "20261107")
        monkeypatch.setattr(cli, "Bucket", lambda: lambda: FakeClient(done))
        monkeypatch.setattr(cli, "heartbeat", lambda ok, summary: self.pings.append(ok))

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

        monkeypatch.setattr(cli, "grade_day", grade)
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
