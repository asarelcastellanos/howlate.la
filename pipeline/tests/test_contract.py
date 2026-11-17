"""The data contract. The files `aggregate` writes must match pipeline/schemas.

The site reads these files and nothing else, so a field renamed here without the
schema changing would break the site with no error on the pipeline side. The
schemas are strict in both directions, so a rename fails twice: the new name is
not allowed and the old one is missing.
"""

import copy
import json
from pathlib import Path

import pytest
import test_write
from fixture_day import SERVICE_DATE, run_day

from howlate_pipeline import DERIVED_BUCKET, aggregate, arrivals, labels

ROOT = Path(__file__).resolve().parents[1]
if not (ROOT / "pyproject.toml").is_file():
    # The container job mounts only pipeline/tests, at /tests, so neither the
    # schemas nor jsonschema are there. The checkout job has both. In a checkout
    # the folder must exist, so a moved or deleted schemas/ fails below.
    pytest.skip("not a pipeline checkout, as in the container job", allow_module_level=True)

from jsonschema import Draft202012Validator  # noqa: E402

SCHEMAS = ROOT / "schemas"
RUN = "20261116T130339Z-ef4438"


def validator(kind: str) -> Draft202012Validator:
    schema = json.loads((SCHEMAS / f"{kind}.schema.json").read_text())
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def kind_of(name: str) -> str:
    """The schema a file is checked against, from its path under the site."""
    return "line" if name.startswith("lines/") else name.removesuffix(".json")


def build(root: Path, *, name_stops: bool = True) -> Path:
    """The site `aggregate` builds from the fixture day, written under `root`."""
    con = run_day(root / "day")
    arrivals.write(con, root / "out", SERVICE_DATE)
    graded = arrivals.connect()
    first, last, days = aggregate.load(graded, root / "out" / "arrivals" / arrivals.VERSION)
    # run_day builds its timetable in this folder.
    catalogue = labels.load(graded, {"LACMTA": root / "day" / "gtfs_bus"})
    if not name_stops:
        # What a stop missing from the timetable's stop list looks like.
        catalogue["stops"].clear()
    site = root / "site"
    aggregate.build(graded, catalogue, site, first, last, days)
    return site


@pytest.fixture(scope="module")
def site(tmp_path_factory) -> Path:
    return build(tmp_path_factory.mktemp("named"))


@pytest.fixture(scope="module")
def nameless_site(tmp_path_factory) -> Path:
    return build(tmp_path_factory.mktemp("nameless"), name_stops=False)


@pytest.fixture(scope="module")
def pointer(site) -> dict:
    """site/current.json as `upload` publishes it. Two runs, so previous is not empty."""
    client = test_write.FakeClient([])
    test_write.publish(client, site, run="20261115T130434Z-e4dc48")
    test_write.publish(client, site, run=RUN)
    return json.loads(client.store[(DERIVED_BUCKET, aggregate.POINTER)])


def documents(site: Path, pointer: dict) -> dict[str, dict]:
    """One produced document of each kind, keyed by the kind of schema it answers to."""
    written = {path.relative_to(site).as_posix(): path for path in sorted(site.rglob("*.json"))}
    return {
        "index": json.loads(written["index.json"].read_text()),
        "status": json.loads(written["status.json"].read_text()),
        "line": json.loads(written["lines/720.json"].read_text()),
        Path(aggregate.POINTER).stem: pointer,
    }


def objects(node, path=()):
    """The path to every object in a document, the root included."""
    if isinstance(node, dict):
        yield path
        for key, value in node.items():
            yield from objects(value, (*path, key))
    elif isinstance(node, list):
        for position, value in enumerate(node):
            yield from objects(value, (*path, position))


def at(document, path):
    for step in path:
        document = document[step]
    return document


def missing_schemas(names: list[str]) -> set[str]:
    """The kinds of these files that have no schema."""
    have = {path.name.removesuffix(".schema.json") for path in SCHEMAS.glob("*.schema.json")}
    return {kind_of(name) for name in names} - have


def test_every_file_aggregate_writes_validates(site, pointer):
    names = sorted(path.relative_to(site).as_posix() for path in site.rglob("*.json"))
    assert names == ["index.json", "lines/720.json", "status.json"]
    for name in names:
        document = json.loads((site / name).read_text())
        errors = [error.message for error in validator(kind_of(name)).iter_errors(document)]
        assert not errors, f"{name}: {errors[:3]}"

    errors = [error.message for error in validator("current").iter_errors(pointer)]
    assert not errors, f"{aggregate.POINTER}: {errors[:3]}"
    assert pointer["previous"] == ["20261115T130434Z-e4dc48"]


def test_a_stop_missing_from_the_timetable_validates_with_null_coordinates(nameless_site):
    document = json.loads((nameless_site / "lines" / "720.json").read_text())
    stops = [stop for direction in document["directions"] for stop in direction["stops"]]
    assert stops
    assert all(stop["lat"] is None and stop["lon"] is None for stop in stops)
    assert not list(validator("line").iter_errors(document))


@pytest.mark.parametrize("kind", ["index", "status", "line", "current"])
def test_renaming_or_adding_a_field_fails_validation(site, pointer, kind):
    document = documents(site, pointer)[kind]
    check = validator(kind)
    assert not list(check.iter_errors(document))

    survivors = []
    for path in objects(document):
        for key in list(at(document, path)):
            renamed = copy.deepcopy(document)
            target = at(renamed, path)
            target[f"{key}_renamed"] = target.pop(key)
            if not list(check.iter_errors(renamed)):
                survivors.append(("renamed", path, key))

        extra = copy.deepcopy(document)
        at(extra, path)["extra_field"] = 1
        if not list(check.iter_errors(extra)):
            survivors.append(("added", path, "extra_field"))
    assert not survivors


def test_every_file_kind_has_a_schema_and_every_schema_a_file_kind(site):
    names = [path.relative_to(site).as_posix() for path in site.rglob("*.json")]
    names.append(Path(aggregate.POINTER).name)
    assert not missing_schemas(names)

    on_disk = {path.name.removesuffix(".schema.json") for path in SCHEMAS.glob("*.schema.json")}
    assert on_disk == {kind_of(name) for name in names}, (
        "a schema describes no file aggregate writes"
    )


def test_a_new_output_file_without_a_schema_is_caught():
    assert missing_schemas(["index.json", "lines/1.json", "leaderboard.json"]) == {"leaderboard"}
