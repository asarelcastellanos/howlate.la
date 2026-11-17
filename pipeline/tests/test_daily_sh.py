"""The daily.sh checks that must agree with the Python ones, and its prompts.

`daily.sh` deploys the job, so it is never run here. The address check is a
function in the script, extracted and run on its own with `bash -c` and compared
with `r2.is_https_address` on the same values, because a value the script lets
through and Python refuses fails every daily run after the copy.
"""

import re
import subprocess
from pathlib import Path

import pytest

from howlate_pipeline import r2

SCRIPT = Path(__file__).resolve().parents[1] / "deploy" / "daily.sh"

pytestmark = pytest.mark.skipif(
    not (SCRIPT.parent.parent / "pyproject.toml").is_file(),
    reason="not a pipeline checkout, as in the container job",
)

GOOD = [
    "https://data.howlate.la",
    "https://Data.HowLate.la",
    "https://pub-4b142eaaa0dc461aa668b007c9f14299.r2.dev",
    "https://0123456789abcdef0123456789abcdef.r2.cloudflarestorage.com",
    "https://x.r2.cloudflarestorage.com",
    "https://localhost",
]
BAD = [
    "https://data.howlate.la:443",
    "https://host?x=1",
    "https://host#f",
    "https://u@host",
    "https://user:pw@host",
    "https://data.howlate.la/",
    "https://data.howlate.la/site",
    "http://data.howlate.la",
    "https://a b.la",
    "https://a,b.la",
    "https://a_b.la",
    "https://exämple.com",
    "https://",
    "https:// ",
    "https://[::1]",
    "data.howlate.la",
    "",
    "https://data.howlate.la ",
    " https://data.howlate.la",
    "https://data.howlate.la\n",
    "https://ho\nst",
    "HTTPS://host",
    "Https://data.howlate.la",
]


def function_text(name: str) -> str:
    text = SCRIPT.read_text()
    match = re.search(rf"^{name}\(\) \{{\n.*?^\}}\n", text, re.S | re.M)
    assert match, f"{name}() is not defined in daily.sh"
    return match.group(0)


def shell_accepts(value: str, locale: str = "C") -> bool:
    done = subprocess.run(
        ["bash", "-c", function_text("is_https_address") + '\nis_https_address "$1"', "_", value],
        env={"PATH": "/usr/bin:/bin", "LC_ALL": locale},
        capture_output=True,
        check=False,
    )
    assert done.returncode in (0, 1), done.stderr
    return done.returncode == 0


@pytest.mark.parametrize("value", GOOD)
def test_the_shell_accepts_what_python_accepts(value):
    assert r2.is_https_address(value) is True
    assert shell_accepts(value) is True


@pytest.mark.parametrize("value", BAD)
def test_the_shell_refuses_what_python_refuses(value):
    assert r2.is_https_address(value) is False
    assert shell_accepts(value) is False


@pytest.mark.parametrize("value", [*GOOD, *BAD])
def test_the_shell_does_not_depend_on_the_locale(value):
    assert shell_accepts(value, "en_US.UTF-8") == shell_accepts(value, "C")


def test_the_script_checks_both_r2_addresses_with_that_function():
    text = SCRIPT.read_text()
    assert 'is_https_address "$R2_ENDPOINT"' in text
    assert 'is_https_address "$R2_PUBLIC_URL"' in text


def test_the_public_url_prompt_does_not_promise_a_skip():
    text = SCRIPT.read_text()
    (prompt,) = re.findall(r'read -rp "[^"]*public data URL[^"]*"', text)
    assert "skip" not in prompt.lower()
    assert "required when R2 is configured" in prompt
    (endpoint_prompt,) = re.findall(r'read -rp "[^"]*R2 endpoint[^"]*"', text)
    assert "Enter to skip R2" in endpoint_prompt


def test_the_script_parses():
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True)
