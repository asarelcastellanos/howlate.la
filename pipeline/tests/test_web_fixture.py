"""The site's browser-test fixture must keep matching the data contract.

web/e2e/fixture/ is a trimmed copy of real `aggregate` output that the browser
job serves to the built site. The fixture is committed, so a schema change that
leaves it behind would pass every pipeline test and then fail in the browser
job, or worse, let the browser tests pass against a shape the site never gets.
The schemas are strict, so a renamed field in either place fails here.
"""

import json
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
# `.parent` stops at the filesystem root, so this is a path that does not exist,
# not an IndexError, when the tests are mounted at /tests in the container job.
FIXTURE = HERE.parent.parent / "web" / "e2e" / "fixture"
if not FIXTURE.is_dir():
    pytest.skip("web/e2e/fixture is absent, as in the container job", allow_module_level=True)

from jsonschema import Draft202012Validator  # noqa: E402

SCHEMAS = HERE.parent / "schemas"
SITE = FIXTURE / "site"


def validator(kind: str) -> Draft202012Validator:
    schema = json.loads((SCHEMAS / f"{kind}.schema.json").read_text())
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def load(path: Path) -> dict:
    """A fixture file that must exist, because the directory does."""
    assert path.is_file(), f"{path.relative_to(FIXTURE)} is missing"
    return json.loads(path.read_text())


def assert_valid(kind: str, path: Path) -> dict:
    document = load(path)
    errors = sorted(validator(kind).iter_errors(document), key=lambda e: list(e.path))
    shown = [f"{'/'.join(map(str, e.path))}: {e.message}"[:200] for e in errors[:5]]
    assert not errors, f"{path.relative_to(FIXTURE)} breaks {kind}.schema.json: {shown}"
    return document


@pytest.fixture(scope="module")
def pointer() -> dict:
    return assert_valid("current", SITE / "current.json")


@pytest.fixture(scope="module")
def run_dir(pointer) -> Path:
    # The pointer's prefix is relative to the bucket root, which the fixture's
    # parent of site/ stands in for. The site reads files from it the same way.
    assert pointer["prefix"] == f"site/runs/{pointer['run']}/"
    path = FIXTURE / pointer["prefix"]
    assert path.is_dir(), f"the pointer names {pointer['prefix']}, which does not exist"
    return path


def test_the_pointer_counts_the_files_of_the_run_it_names(pointer, run_dir):
    held = [p for p in run_dir.rglob("*") if p.is_file()]
    assert pointer["files"] == len(held)


def test_every_file_of_the_run_matches_its_schema(run_dir):
    for name in ("status", "network", "health"):
        assert_valid(name, run_dir / f"{name}.json")
    index = assert_valid("index", run_dir / "index.json")
    listed = {entry["line"] for entry in index["lines"]}
    assert listed, "the index lists no line"
    for line in listed:
        assert_valid("line", run_dir / "lines" / f"{line}.json")


def test_the_index_lists_exactly_the_line_files(run_dir):
    index = load(run_dir / "index.json")
    listed = sorted(entry["line"] for entry in index["lines"])
    held = sorted(p.stem for p in (run_dir / "lines").glob("*.json"))
    assert listed == held


def test_each_index_entry_agrees_with_its_line_file(run_dir):
    # The index is what search and the ranking read, and the line file is what
    # the page shows. A fixture edited in one place only would hide a mismatch.
    for entry in load(run_dir / "index.json")["lines"]:
        doc = load(run_dir / "lines" / f"{entry['line']}.json")
        for field in ("label", "via", "mode", "agency"):
            assert entry[field] == doc[field], (entry["line"], field)
        assert entry["to"] == [d["to"] for d in doc["directions"]], entry["line"]
        assert entry["n"] == sum(d["n"] for d in doc["directions"]), entry["line"]
