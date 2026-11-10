"""The command line, end to end on the fixture day, with no cloud at all.

Each command runs as a separate process, the way the container's entry point
runs it. Credentials are pointed at a file that does not exist, so any attempt
to reach Cloud Storage fails the test instead of quietly using a developer's
login.
"""

import json
import os
import subprocess
import sys

import pytest
from fixture_day import SERVICE_DATE, build_raw, build_timetable


def cli(*args: str, cwd) -> subprocess.CompletedProcess:
    env = {**os.environ, "GOOGLE_APPLICATION_CREDENTIALS": "/nonexistent/credentials.json"}
    # The child runs in another directory, so a relative PYTHONPATH would point
    # nowhere and quietly fall back to whatever copy is installed.
    if env.get("PYTHONPATH"):
        env["PYTHONPATH"] = os.pathsep.join(
            os.path.abspath(part) for part in env["PYTHONPATH"].split(os.pathsep)
        )
    env.pop("GOOGLE_CLOUD_PROJECT", None)
    return subprocess.run(
        [sys.executable, "-m", "howlate_pipeline", *args],
        cwd=cwd, env=env, capture_output=True, text=True, timeout=120,
    )  # fmt: skip


@pytest.fixture(scope="module")
def graded(tmp_path_factory):
    root = tmp_path_factory.mktemp("cli")
    build_raw(root / "raw")
    build_timetable(root / "gtfs" / "gtfs_bus")
    day = f"{SERVICE_DATE[:4]}-{SERVICE_DATE[4:6]}-{SERVICE_DATE[6:]}"
    result = cli(
        "arrivals", "--service-date", day, "--raw-dir", str(root / "raw"),
        "--gtfs-dir", str(root / "gtfs"), "--out", str(root / "out"),
        "--cache", str(root / "cache"), "--no-upload", cwd=root,
    )  # fmt: skip
    return root, result


def test_arrivals_grades_a_day_from_local_files(graded):
    root, result = graded
    # The fixture is far too small for the real ranges, so the day's checks
    # fail (exit 2) while it is still written. Anything else is a crash.
    assert result.returncode == 2, result.stderr
    out = root / "out"
    for table in ("arrivals", "trips"):
        assert (out / table / "v2" / "service_date=2026-08-18" / "part-0.parquet").exists()
    report = json.loads((out / "reports/v2/service_date=2026-08-18/report.json").read_text())
    assert report["stats"]["scheduled_stops"] == 8


def test_aggregate_builds_the_site_from_local_files(graded):
    root, _ = graded
    result = cli(
        "aggregate", "--arrivals", str(root / "out" / "arrivals" / "v2"),
        "--gtfs-dir", str(root / "gtfs"), "--out", str(root / "site"),
        "--cache", str(root / "cache"), "--no-upload", cwd=root,
    )  # fmt: skip
    assert result.returncode == 0, result.stderr
    index = json.loads((root / "site" / "index.json").read_text())
    assert [line["line"] for line in index["lines"]] == ["720"]
    assert (root / "site" / "lines" / "720.json").exists()
    assert json.loads((root / "site" / "status.json").read_text())["days"] == 1


def test_a_gtfs_dir_without_timetables_is_refused(tmp_path):
    result = cli(
        "arrivals", "--service-date", "2026-08-18", "--raw-dir", str(tmp_path),
        "--gtfs-dir", str(tmp_path), "--no-upload", cwd=tmp_path,
    )  # fmt: skip
    assert result.returncode != 0
    assert "no gtfs_bus/ or gtfs_rail/" in result.stderr
