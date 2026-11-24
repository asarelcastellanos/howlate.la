"""The backfill-vm.sh checks that decide what the VM is allowed to run.

The script creates a VM, so it is never run for real here. A stand-in `gcloud`
on the PATH records its arguments, which shows what the script would have
created without calling Google.
"""

import re
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "deploy" / "backfill-vm.sh"

pytestmark = pytest.mark.skipif(
    not (SCRIPT.parent.parent / "pyproject.toml").is_file(),
    reason="not a pipeline checkout, as in the container job",
)

GOOD = [
    "pipeline/scripts/count_positions.py",
    "pipeline/scripts/sub/dir/a.py",
]
BAD = [
    "pipeline/scripts/count_positions.sh",
    "pipeline/scripts/count_positions.py.txt",
    "pipeline/scripts/",
    "pipeline/",
    "scripts/count_positions.py",
    "collector/src/howlate_collector/record.py",
    "pipeline_other/a.py",
    "/pipeline/scripts/a.py",
    "pipeline/../collector/a.py",
    "pipeline/scripts/../../collector/a.py",
    "pipeline/a,b.py",
    "pipeline/...py",
    "pipeline/.py",
    "pipeline/scripts/.hidden.py",
    "pipeline/my script.py",
    "",
]


def function_text(name: str) -> str:
    match = re.search(rf"^{name}\(\) \{{\n.*?^\}}\n", SCRIPT.read_text(), re.S | re.M)
    assert match, f"{name}() is not defined in backfill-vm.sh"
    return match.group(0)


def path_accepted(value: str) -> bool:
    done = subprocess.run(
        ["bash", "-c", function_text("valid_script_path") + '\nvalid_script_path "$1"', "_", value],
        capture_output=True,
        check=False,
    )
    assert done.returncode in (0, 1), done.stderr
    return done.returncode == 0


@pytest.mark.parametrize("value", GOOD)
def test_a_script_under_pipeline_is_accepted(value):
    assert path_accepted(value)


@pytest.mark.parametrize("value", BAD)
def test_a_script_outside_pipeline_or_not_python_is_refused(value):
    assert not path_accepted(value)


def run_with_fake_gcloud(tmp_path: Path, *args: str) -> tuple[int, list[str]]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    record = tmp_path / "calls"
    fake = bin_dir / "gcloud"
    fake.write_text(f'#!/bin/sh\nprintf \'%s\\n\' "$*" >>"{record}"\n')
    fake.chmod(0o755)
    done = subprocess.run(
        ["bash", str(SCRIPT), *args],
        env={"PATH": f"{bin_dir}:/usr/bin:/bin"},
        capture_output=True,
        text=True,
        check=False,
    )
    calls = record.read_text().splitlines() if record.exists() else []
    return done.returncode, calls


def test_a_bad_script_path_stops_before_any_gcloud_call(tmp_path):
    code, calls = run_with_fake_gcloud(
        tmp_path, "--script", "collector/a.py", "main", "2026-11-01", "2026-11-02"
    )
    assert (code, calls) == (1, [])


def test_the_three_argument_call_still_creates_the_backfill_vm(tmp_path):
    code, calls = run_with_fake_gcloud(tmp_path, "release/v0.3.0", "2026-11-01", "2026-11-02")
    assert code == 0
    create = next(c for c in calls if c.startswith("compute instances create"))
    assert (
        "--metadata howlate-ref=release/v0.3.0,howlate-first=2026-11-01,howlate-last=2026-11-02 "
        in create
    )
    assert "howlate-script" not in create
    assert any(c.startswith("scheduler jobs describe howlate-daily") for c in calls)


def test_a_run_id_that_could_escape_the_prefix_stops_before_any_gcloud_call(tmp_path):
    code, calls = run_with_fake_gcloud(
        tmp_path, "--script", "pipeline/a.py", "--run", "../x", "main", "2026-11-01", "2026-11-02"
    )
    assert (code, calls) == (1, [])
