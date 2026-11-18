"""Builds web/e2e/fixture/ from a full `aggregate` output folder.

    python3 web/e2e/make_fixture.py <site folder with index.json, status.json,
        network.json and lines/> web/e2e/fixture
    python3 web/e2e/make_fixture.py --health web/e2e/fixture
    python3 web/e2e/make_fixture.py --estimates web/e2e/fixture
    cd web && npx prettier --write e2e/fixture

The result is trimmed, so its totals do not match the full data. See README.md.
`--health` rewrites only health.json and the pointer's file count in a fixture
that exists, for when the aggregate output is no longer at hand. `--estimates`
adds the `est` counts to a fixture made from a run that predates them.
"""

import json
import shutil
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

# health.json comes from the pipeline's own builder, so its shape cannot drift
# from the one the daily job writes. The module imports only the standard
# library, so no install is needed.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "pipeline" / "src"))
from howlate_pipeline import health  # noqa: E402

RUN = "20261116T130339Z"
# 720 and 761 are Rapid, 901 is the G Line busway, 697 has the least data, 801
# and 804 are rail. 550 is small and gets one direction below.
LINES = ["4", "550", "697", "720", "761", "801", "804", "901"]
ONE_DIRECTION = ("550", 1)  # keep direction id 1 only
MAX_STOPS = 10


def evenly(stops, count):
    """`count` stops spread over the route, first and last included."""
    if len(stops) <= count:
        return stops
    keep = sorted({round(i * (len(stops) - 1) / (count - 1)) for i in range(count)})
    return [stops[i] for i in keep]


# The newest day's checks, with the labels and ranges the pipeline's
# report.py uses. matched_rate and coverage are ranges, feeds and silent_lines
# are counts, and feeds expects 2.
CHECKS = [
    ("matched_rate", "range", "observations matching a scheduled stop, or a trip listed only under a later-start service", 99.98765, (99.9, 100.0)),
    ("coverage", "range", "scheduled stops with a timed arrival, not counting interpolated ones", 71.9, (55.0, 90.0)),
    ("absurd_pct", "range", "delays beyond an hour", 0.014781, (0.0, 0.5)),
    ("feeds", "count", "feeds contributing scheduled stops", 2, 2),
    ("silent_lines", "count", "lines scheduled today but never seen", 0, 0),
]  # fmt: skip
# Days before last_day. The report for MISSING_DAY is left out, as the pipeline
# leaves out a day it never graded, and FAILED_DAY fails its coverage check.
MISSING_DAY = 3
FAILED_DAY = 5
STRIP_DAYS = 14
# The source run predates the estimate, so it has no `est` counts. These are made
# up, like the numbers in health.json: a fifth of every bus count, against the
# 20 to 24 percent of weekday bus stops that were estimated on 10 to 14 November
# 2026, and none for rail, which is never estimated. They give the browser tests
# an estimated figure to look for.
BUS_ESTIMATED_SHARE = 0.2
ESTIMATED_PCT = 18.4  # of scheduled stops, on each day in health.json


def estimated(n: int, mode: str) -> int:
    return round(n * BUS_ESTIMATED_SHARE) if mode == "bus" else 0


def report(day: str, age: int) -> dict:
    """One saved daily report in the shape report.py writes, with fixed numbers."""
    failed = age == FAILED_DAY
    rows = []
    for name, kind, label, value, bound in CHECKS:
        if name == "coverage" and failed:
            value = 49.6
        row = {"name": name, "kind": kind, "label": label, "value": value}
        if kind == "range":
            low, high = bound
            row |= {"low": low, "high": high, "ok": low <= value <= high}
        else:
            row |= {"expect": bound, "ok": value == bound}
        rows.append(row)
    return {
        "service_date": day,
        "pipeline_version": health.__version__,
        "stats": {
            "coverage": 49.6 if failed else 71.9,
            "interpolated_pct": ESTIMATED_PCT,
            "observations": 520000 + 3000 * age,
            "explained_trips": 338 if age == 1 else 0,
            "explained_pct": 1.0 if age == 1 else 0.0,
        },
        "checks": rows,
        "ok": all(row["ok"] for row in rows),
    }


def write_health(out: Path):
    """Adds health.json to the run the pointer names, and makes the pointer count it."""
    pointer_path = out / "site" / "current.json"
    pointer = json.loads(pointer_path.read_text())
    run_dir = out / pointer["prefix"]
    status = json.loads((run_dir / "status.json").read_text())
    last = date.fromisoformat(status["last_day"])
    with tempfile.TemporaryDirectory() as tmp:
        reports = Path(tmp)
        for age in range(STRIP_DAYS):
            if age == MISSING_DAY:
                continue
            day = (last - timedelta(days=age)).isoformat()
            path = reports / f"service_date={day}" / "report.json"
            path.parent.mkdir()
            path.write_text(json.dumps(report(day, age)))
        document = health.document(reports, status["last_day"], status["days"])
    (run_dir / "health.json").write_text(json.dumps(document))
    pointer["files"] = sum(1 for path in run_dir.rglob("*") if path.is_file())
    pointer_path.write_text(json.dumps(pointer))


def write_estimates(out: Path):
    """Adds `est` beside every `n` in the run the pointer names, bus only."""
    pointer = json.loads((out / "site" / "current.json").read_text())
    run_dir = out / pointer["prefix"]

    def edit(name: str, change):
        path = run_dir / name
        document = json.loads(path.read_text())
        change(document)
        path.write_text(json.dumps(document))

    def index(document):
        for entry in document["lines"]:
            entry["est"] = estimated(entry["n"], entry["mode"])

    def line(document):
        for direction in document["directions"]:
            direction["all"]["est"] = estimated(direction["all"]["n"], document["mode"])
            for stop in direction["stops"]:
                stop["est"] = estimated(stop["n"], document["mode"])

    def network(document):
        for scope in ("bus", "rail"):
            all_ = document[scope]["all"]
            all_["est"] = estimated(all_["n"], scope)
        document["network"]["all"]["est"] = document["bus"]["all"]["est"]

    def status(document):
        document["estimated_arrivals"] = json.loads((run_dir / "network.json").read_text())[
            "network"
        ]["all"]["est"]

    edit("index.json", index)
    for path in sorted((run_dir / "lines").glob("*.json")):
        edit(f"lines/{path.name}", line)
    edit("network.json", network)
    edit("status.json", status)


def main(source: Path, out: Path):

    def read(path):
        return json.loads((source / path).read_text())

    run_dir = out / "site" / "runs" / RUN
    shutil.rmtree(out / "site", ignore_errors=True)
    (run_dir / "lines").mkdir(parents=True)

    entries = {e["line"]: e for e in read("index.json")["lines"]}
    kept = []
    for line in LINES:
        doc = read(f"lines/{line}.json")
        if line == ONE_DIRECTION[0]:
            doc["directions"] = [d for d in doc["directions"] if d["id"] == ONE_DIRECTION[1]]
        for direction in doc["directions"]:
            direction["stops"] = evenly(direction["stops"], MAX_STOPS)
            # The source predates these two trims. Dropping them is a no-op on a newer run.
            for stop in direction["stops"]:
                stop["all"].pop("n", None)
                for cell in stop["cells"]:
                    cell.pop("ontime", None)
        entry = entries[line]
        entry["to"] = [d["to"] for d in doc["directions"]]
        if len(doc["directions"]) == 1:
            # The index totals a line over its directions, so one direction is its own total.
            only = doc["directions"][0]
            entry.update(only["all"], sched=only["sched"])
        kept.append(entry)
        (run_dir / "lines" / f"{line}.json").write_text(json.dumps(doc))

    index = read("index.json")
    index["lines"] = kept
    (run_dir / "index.json").write_text(json.dumps(index))
    for name in ("status.json", "network.json"):
        shutil.copy(source / name, run_dir / name)
    pointer = {"run": RUN, "prefix": f"site/runs/{RUN}/", "files": len(kept) + 4, "previous": []}
    (out / "site" / "current.json").write_text(json.dumps(pointer))
    write_estimates(out)
    write_health(out)


if __name__ == "__main__":
    if sys.argv[1] == "--health":
        write_health(Path(sys.argv[2]))
    elif sys.argv[1] == "--estimates":
        write_estimates(Path(sys.argv[2]))
    else:
        main(Path(sys.argv[1]), Path(sys.argv[2]))
