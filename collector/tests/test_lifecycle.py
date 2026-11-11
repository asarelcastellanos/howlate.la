"""Checks on the raw bucket's lifecycle rule before anyone applies it.

Run with:  .venv/bin/python collector/tests/test_lifecycle.py

The rule moves old vehicle positions to cheaper storage classes. A mistake
here is applied by Google to every matching object, with no undo, so the file
is checked rather than trusted:

- Nothing is ever deleted. The raw archive is append-only and the one part of
  this project that cannot be rebuilt.
- Only vehicle_positions/ moves. gtfs/ holds the timetables every regrade
  reads, and moving it would add a retrieval fee to every one of them.
- Positions go to Coldline at 30 days and Archive at 365. The daily job grades
  the seven days ending two days back, each with the UTC partitions either
  side of it, so it reads raw files up to about ten days old and never pays a
  retrieval fee; a backfill or regrade of older days does, at $0.02/GB
  (Coldline) or $0.05/GB (Archive).
- Each rule matches only the class it moves from, so an object moves forward
  one step at a time and never back to a warmer class.
- The file holds the rule list and nothing else, and each rule only the keys
  checked here. gcloud applies a "lifecycle" key in place of "rule" when one
  is present, and any extra condition narrows a rule, so neither may slip in
  unchecked.
"""

import json
import sys
from pathlib import Path

RULE = Path(__file__).resolve().parents[1] / "deploy" / "raw-lifecycle.json"


def check(rules: list[dict]) -> list[str]:
    """Everything wrong with the rule, or an empty list."""
    problems = []
    for rule in rules:
        if set(rule) != {"action", "condition"}:
            problems.append(f"a rule holds only action and condition: {sorted(rule)}")
        if set(rule.get("action", {})) != {"type", "storageClass"}:
            problems.append(f"unexpected action keys: {sorted(rule.get('action', {}))}")
        expected_keys = {"age", "matchesPrefix", "matchesStorageClass"}
        if set(rule.get("condition", {})) != expected_keys:
            problems.append(f"unexpected condition keys: {sorted(rule.get('condition', {}))}")
    actions = [rule["action"]["type"] for rule in rules]
    if any(action != "SetStorageClass" for action in actions):
        problems.append(f"only SetStorageClass is allowed, found {actions}")
    for rule in rules:
        prefixes = rule["condition"].get("matchesPrefix")
        if prefixes != ["vehicle_positions/"]:
            problems.append(f"a rule must match vehicle_positions/ and nothing else: {prefixes}")
    steps = sorted(
        (
            rule["condition"].get("age"),
            rule["condition"].get("matchesStorageClass"),
            rule["action"].get("storageClass"),
        )
        for rule in rules
    )
    expected = [(30, ["STANDARD"], "COLDLINE"), (365, ["COLDLINE"], "ARCHIVE")]
    if steps != expected:
        problems.append(f"expected {expected}, found {steps}")
    return problems


def test_the_rule_in_the_repo_passes():
    document = json.loads(RULE.read_text())
    # gcloud would apply a "lifecycle" key instead of "rule" if one were here.
    assert set(document) == {"rule"}, sorted(document)
    assert check(document["rule"]) == [], check(document["rule"])


def test_a_delete_is_caught():
    rules = json.loads(RULE.read_text())["rule"]
    rules.append({"action": {"type": "Delete"}, "condition": {"age": 3650}})
    assert any("only SetStorageClass" in problem for problem in check(rules))


def test_moving_the_timetables_is_caught():
    rules = json.loads(RULE.read_text())["rule"]
    rules[0]["condition"]["matchesPrefix"].append("gtfs/")
    assert any("nothing else" in problem for problem in check(rules))


def test_an_extra_condition_is_caught():
    # Conditions are ANDed, so this one would stop the rule ever firing.
    rules = json.loads(RULE.read_text())["rule"]
    rules[0]["condition"]["createdBefore"] = "2020-01-01"
    assert any("condition keys" in problem for problem in check(rules))


def test_a_rule_with_no_prefix_is_caught():
    # No prefix would match every object in the bucket.
    rules = json.loads(RULE.read_text())["rule"]
    del rules[1]["condition"]["matchesPrefix"]
    assert check(rules)


def test_a_wrong_age_or_class_is_caught():
    rules = json.loads(RULE.read_text())["rule"]
    rules[0]["condition"]["age"] = 7
    assert check(rules)
    rules = json.loads(RULE.read_text())["rule"]
    rules[1]["condition"]["matchesStorageClass"] = ["STANDARD", "COLDLINE"]
    assert check(rules)


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"ok  {test.__name__}")
    print(f"{len(tests)} passed")
    sys.exit(0)
