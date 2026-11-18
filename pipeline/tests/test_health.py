"""health.json: what the behind-the-scenes page reads from the saved daily reports.

The reports in the bucket come in two shapes. Days graded by 0.3.0 and earlier
name the join check `join_rate` and have no explained_* stats. Days graded by
0.4.0 name it `matched_rate` and have them. Both must produce a row, and a
report that cannot is skipped, never fatal.
"""

import json
import re

from howlate_pipeline import aggregate, health

RANGE = ("coverage", "scheduled stops with a timed arrival", 81.13352126715155, 55.0, 90.0)
COUNT = ("silent_lines", "lines scheduled today but never seen", 0, 0)


def report(day, *, old=False, fail=(), extra=None):
    """A saved report as the pipeline writes it, with the checks named in `fail` failing."""
    join = "join_rate" if old else "matched_rate"
    found = [
        {"name": join, "kind": "range", "label": "observations matching a scheduled stop",
         "value": 100.0, "low": 99.9, "high": 100.0, "ok": True},
        {"name": RANGE[0], "kind": "range", "label": RANGE[1], "value": RANGE[2],
         "low": RANGE[3], "high": RANGE[4], "ok": True},
        {"name": COUNT[0], "kind": "count", "label": COUNT[1], "value": COUNT[2],
         "expect": COUNT[3], "ok": True},
    ]  # fmt: skip
    for entry in found:
        if entry["name"] in fail:
            entry["ok"] = False
    stats = {"coverage": 81.13352126715155, "observations": 526528, "scheduled_stops": 642070}
    if not old:
        stats |= {"explained_trips": 337, "explained_pct": 1.0624316275677648}
    return {
        "service_date": day,
        "pipeline_version": "0.3.0" if old else "0.4.1",
        "stats": stats,
        "checks": found,
        "ok": all(entry["ok"] for entry in found),
    } | (extra or {})


def write(root, *documents):
    for document in documents:
        path = root / f"service_date={document['service_date']}" / "report.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(document))
    return root


def three_days(root):
    """A passing day, a day failing a check, and a 0.3.0 day with the old check name."""
    return write(
        root,
        report("2026-08-18"),
        report("2026-08-17", fail=("coverage",)),
        report("2026-08-16", old=True),
    )


def test_recent_is_newest_first_with_ok_and_failed_from_the_report(tmp_path):
    out = health.document(three_days(tmp_path), "2026-08-18", 3)

    assert [(day["service_date"], day["ok"], day["failed"]) for day in out["recent"]] == [
        ("2026-08-18", True, []),
        ("2026-08-17", False, ["coverage"]),
        ("2026-08-16", True, []),
    ]
    assert out["recent"][0] == {
        "service_date": "2026-08-18",
        "ok": True,
        "failed": [],
        "coverage_pct": 81.1,
        "estimated_pct": 0,
        "explained_trips": 337,
        "explained_pct": 1.1,
        "observations": 526528,
    }


def test_estimated_pct_is_the_interpolated_share_and_zero_for_older_reports(tmp_path):
    newer = report("2026-08-18", extra={"stats": {
        "coverage": 70.0, "observations": 1, "scheduled_stops": 2, "interpolated_pct": 22.46,
    }})  # fmt: skip
    out = health.document(write(tmp_path, newer, report("2026-08-17")), "2026-08-18", 2)
    assert [day["estimated_pct"] for day in out["recent"]] == [22.5, 0]


def test_a_report_from_before_the_explained_fields_gives_zeros(tmp_path):
    out = health.document(three_days(tmp_path), "2026-08-18", 3)
    old = out["recent"][2]
    assert (old["explained_trips"], old["explained_pct"]) == (0, 0)


def test_recent_stops_at_fourteen_days(tmp_path):
    write(tmp_path, *(report(f"2026-08-{day:02d}") for day in range(1, 19)))
    out = health.document(tmp_path, "2026-08-18", 18)
    days = [day["service_date"] for day in out["recent"]]
    assert days == [f"2026-08-{day:02d}" for day in range(18, 4, -1)]
    assert out["days"] == 18  # every graded day, not only the ones listed


def test_checks_are_last_days_with_the_reports_labels(tmp_path):
    out = health.document(three_days(tmp_path), "2026-08-18", 3)
    assert [check["name"] for check in out["checks"]] == [
        "matched_rate",
        "coverage",
        "silent_lines",
    ]
    assert out["checks"][1] == {
        "name": "coverage",
        "kind": "range",
        "label": "scheduled stops with a timed arrival",
        "ok": True,
        "value": 81.13352126715155,
        "low": 55.0,
        "high": 90.0,
    }
    assert out["checks"][2]["expected"] == 0 and "low" not in out["checks"][2]


def test_checks_are_the_report_for_last_day_even_when_older_reports_differ(tmp_path):
    older = report("2026-08-17", old=True, fail=("coverage",))
    write(tmp_path, report("2026-08-18"), older, report("2026-08-16", old=True))
    out = health.document(tmp_path, "2026-08-18", 3)
    assert [check["name"] for check in out["checks"]] == [
        "matched_rate",
        "coverage",
        "silent_lines",
    ]
    assert all(check["ok"] for check in out["checks"])  # the 08-17 failure is not shown


def test_checks_are_empty_when_the_report_for_last_day_cannot_be_read(tmp_path, capsys):
    """Showing an older day's checks next to a newer last_day would read as today's result."""
    write(tmp_path, report("2026-08-17", fail=("coverage",)), report("2026-08-16", old=True))
    unreadable = tmp_path / "service_date=2026-08-18" / "report.json"
    unreadable.parent.mkdir()
    unreadable.write_text('{"service_date": "2026-0')

    out = health.document(tmp_path, "2026-08-18", 3)

    assert out["checks"] == []
    assert out["last_day"] == "2026-08-18"
    assert [day["service_date"] for day in out["recent"]] == ["2026-08-17", "2026-08-16"]
    assert "skipped the report in service_date=2026-08-18" in capsys.readouterr().out


def test_checks_are_empty_when_last_day_has_no_report_at_all(tmp_path):
    write(tmp_path, report("2026-08-17"), report("2026-08-16"))
    out = health.document(tmp_path, "2026-08-18", 3)
    assert out["checks"] == []
    assert [day["service_date"] for day in out["recent"]] == ["2026-08-17", "2026-08-16"]


def test_a_count_check_publishes_its_expect_as_expected(tmp_path):
    # Every report check in the fixtures expects 0, which a constant 0 would also satisfy.
    two = report("2026-08-18", fail=("silent_lines",))
    count = next(check for check in two["checks"] if check["kind"] == "count")
    count |= {"value": 5, "expect": 2}
    write(tmp_path, two)

    out = health.document(tmp_path, "2026-08-18", 1)

    published = next(check for check in out["checks"] if check["name"] == "silent_lines")
    assert published == {
        "name": "silent_lines",
        "kind": "count",
        "label": COUNT[1],
        "ok": False,
        "value": 5,
        "expected": 2,
    }


def test_a_day_with_no_report_is_absent(tmp_path):
    write(tmp_path, report("2026-08-18"), report("2026-08-16"))
    out = health.document(tmp_path, "2026-08-18", 3)
    assert [day["service_date"] for day in out["recent"]] == ["2026-08-18", "2026-08-16"]


def test_a_report_the_run_has_no_arrivals_for_is_left_out(tmp_path):
    write(tmp_path, report("2026-08-19"), report("2026-08-18"))
    out = health.document(tmp_path, "2026-08-18", 1)
    assert [day["service_date"] for day in out["recent"]] == ["2026-08-18"]


def test_no_reports_gives_empty_lists_and_what_the_run_knows(tmp_path):
    for where in (None, tmp_path / "missing", tmp_path):
        out = health.document(where, "2026-08-18", 3)
        assert (out["recent"], out["checks"]) == ([], [])
        assert (out["last_day"], out["days"]) == ("2026-08-18", 3)
        assert out["pipeline_version"] == health.__version__


def test_a_report_that_cannot_be_read_is_skipped_not_fatal(tmp_path, capsys):
    write(tmp_path, report("2026-08-18"))
    (tmp_path / "service_date=2026-08-17").mkdir()
    (tmp_path / "service_date=2026-08-17" / "report.json").write_text('{"service_date": "2026-0')
    no_stats = report("2026-08-16")
    del no_stats["stats"]
    write(tmp_path, no_stats, report("2026-08-15", extra={"service_date": "yesterday"}))

    out = health.document(tmp_path, "2026-08-18", 4)
    assert [day["service_date"] for day in out["recent"]] == ["2026-08-18"]
    assert capsys.readouterr().out.count("skipped") == 3


def test_nothing_secret_or_internal_reaches_the_file(tmp_path):
    """The file is public, so only the fields named in health.py may come through."""
    leaks = {
        "agencies": [{"agency": "gs://howlate-derived/reports/v2/", "lines": 1}],
        "notes": ["copied to https://abc123.r2.cloudflarestorage.com by ops@howlate.la"],
        "error": "Traceback: 403 on howlate-raw from vm-1.internal.example.com",
    }
    poisoned = report("2026-08-18", extra=leaks)
    poisoned["checks"][0] |= {"error": leaks["error"], "bucket": "howlate-derived"}
    poisoned["stats"] |= {"host": "vm-1.internal.example.com"}
    write(tmp_path, poisoned, report("2026-08-17", old=True))

    text = json.dumps(health.document(tmp_path, "2026-08-18", 2))
    assert not re.search(
        r"howlate-(raw|derived)|gs://|https?://|cloudflare|@|\.internal|\.example\.com|Traceback",
        text,
    )


class Listed:
    def __init__(self, name):
        self.name = name

    def download_to_filename(self, target):
        target.write_text(self.name)


class Listing:
    """A bucket that only lists and downloads, so a write would raise."""

    def __init__(self, names):
        self.names = names

    def list_blobs(self, bucket, prefix):
        return [Listed(name) for name in self.names if name.startswith(prefix)]


def test_the_fetch_downloads_only_the_newest_fourteen_reports_into_its_own_folder(tmp_path):
    days = [f"2026-08-{day:02d}" for day in range(1, 21)]
    names = [f"reports/v2/service_date={day}/report.json" for day in days]
    names += [f"arrivals/v2/service_date={day}/part-0.parquet" for day in days]
    # Other blobs under the reports folder are not reports. One sits after its
    # day's report in the listing, and one is the only blob of a newer day.
    names += ["reports/v2/service_date=2026-08-20/report.json.tmp"]
    names += ["reports/v2/service_date=2026-08-21/notes.txt"]
    reports = tmp_path / "reports"
    stale = reports / "service_date=2026-01-01" / "report.json"  # left over from an earlier run
    stale.parent.mkdir(parents=True)
    stale.write_text(json.dumps(report("2026-01-01")))

    aggregate.fetch_arrivals(Listing(names), tmp_path / "graded", reports=reports)

    got = sorted(path.parent.name for path in reports.rglob("report.json"))
    assert got == [f"service_date={day}" for day in days[-health.RECENT_DAYS :]]
    assert not stale.exists()
    assert not any(path.name != "report.json" for path in reports.rglob("*") if path.is_file())
    # Each file is the blob that was named report.json, which the fake writes as its name.
    assert {path.read_text() for path in reports.rglob("report.json")} == {
        f"reports/v2/service_date={day}/report.json" for day in days[-health.RECENT_DAYS :]
    }
    assert len(list((tmp_path / "graded").rglob("*.parquet"))) == 20


def test_a_stale_report_from_an_earlier_run_never_reaches_recent(tmp_path):
    names = [f"reports/v2/service_date=2026-08-{day:02d}/report.json" for day in (17, 18)]
    reports = tmp_path / "reports"
    write(reports, report("2026-01-01"))  # a real, readable report left in the folder

    class Real(Listed):
        def download_to_filename(self, target):
            target.write_text(json.dumps(report(self.name.split("=")[1].split("/")[0])))

    class RealListing(Listing):
        def list_blobs(self, bucket, prefix):
            return [Real(name) for name in self.names if name.startswith(prefix)]

    aggregate.fetch_arrivals(RealListing(names), tmp_path / "graded", reports=reports)
    out = health.document(reports, "2026-08-18", 2)
    assert [day["service_date"] for day in out["recent"]] == ["2026-08-18", "2026-08-17"]
