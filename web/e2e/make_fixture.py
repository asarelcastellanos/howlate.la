"""Builds web/e2e/fixture/ from a full `aggregate` output folder.

    python3 web/e2e/make_fixture.py <site folder with index.json, status.json,
        network.json and lines/> web/e2e/fixture
    python3 web/e2e/make_fixture.py --health web/e2e/fixture
    python3 web/e2e/make_fixture.py --estimates web/e2e/fixture
    python3 web/e2e/make_fixture.py --commute web/e2e/fixture
    cd web && npx prettier --write e2e/fixture

The result is trimmed, so its totals do not match the full data. See README.md.
`--health` rewrites only health.json and the pointer's file count in a fixture
that exists, for when the aggregate output is no longer at hand. `--estimates`
adds the `est` counts to a fixture made from a run that predates them. `--commute`
writes the commute files, which no aggregate output holds, and counts them in the
pointer.
"""

import json
import random
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


UNIT = 10
COMMUTE_STOPS = {
    "720": {
        0: [
            ("10001", "Wilshire / Westwood", 34.0583, -118.4413),
            ("10002", "Wilshire / Veteran", 34.0579, -118.4492),
            ("10003", "Wilshire / Bundy", 34.0521, -118.4660),
            ("10004", "Wilshire / Sepulveda", 34.0515, -118.4478),
            ("10005", "Wilshire / Fairfax", 34.0618, -118.3611),
            ("10006", "Wilshire / Vermont", 34.0620, -118.2915),
        ],
        1: [
            ("20006", "Wilshire / Vermont", 34.0622, -118.2917),
            ("20005", "Wilshire / Fairfax", 34.0620, -118.3613),
            ("20004", "Wilshire / Sepulveda", 34.0517, -118.4480),
            ("20003", "Wilshire / Bundy", 34.0523, -118.4662),
            ("20002", "Wilshire / Veteran", 34.0581, -118.4494),
            ("20001", "Wilshire / Westwood", 34.0585, -118.4415),
        ],
    },
    "4": {
        0: [
            ("30001", "Santa Monica / Vermont", 34.0906, -118.2916),
            ("30002", "Santa Monica / Western", 34.0905, -118.3089),
            ("30003", "Santa Monica / La Brea", 34.0904, -118.3441),
            ("30004", "Santa Monica / Fairfax", 34.0903, -118.3612),
        ],
        1: [
            ("40004", "Santa Monica / Fairfax", 34.0905, -118.3614),
            ("40003", "Santa Monica / La Brea", 34.0906, -118.3443),
            ("40002", "Santa Monica / Western", 34.0907, -118.3091),
            ("40001", "Santa Monica / Vermont", 34.0908, -118.2918),
        ],
    },
}
SCHEDULED_GAPS = {"720": [0, 330, 420, 360, 780, 840], "4": [0, 300, 480, 360]}
COMMUTE_FILES = [
    ("720", 0, "weekday", date(2026, 11, 2), 12, [25200, 27000, 28800, 30600, 34200], [12, 12, 12, 12, 7]),
    ("720", 1, "weekday", date(2026, 11, 2), 12, [25200, 28800, 32400], [12, 12, 12]),
    ("720", 0, "saturday", date(2026, 9, 26), 8, [28800, 32400], [8, 8]),
    ("4", 0, "weekday", date(2026, 11, 2), 12, [27000, 30600], [12, 12]),
    ("4", 1, "weekday", date(2026, 11, 2), 12, [27000, 30600], [12, 12]),
]  # fmt: skip


def service_days(first: date, count: int, kind: str) -> list[str]:
    out = []
    day = first
    while len(out) < count:
        if kind == "saturday" or day.weekday() < 5:
            out.append(day.strftime("%Y%m%d"))
        day += timedelta(days=7 if kind == "saturday" else 1)
    return out


def commute_file(line, direction, kind, first, count, starts, ran, rng):
    stops = COMMUTE_STOPS[line][direction]
    days = service_days(first, count, kind)
    gaps = SCHEDULED_GAPS[line][: len(stops)]
    offsets = [sum(gaps[: k + 1]) for k in range(len(stops))]
    patterns = []
    for start, how_many in zip(starts, ran):
        day_indexes = list(range(count - how_many, count))
        columns = []
        for _ in day_indexes:
            late = rng.choice([-60, -30, 0, 30, 60, 120, 180, 300, 480])
            actual, previous = [], 0
            for offset in offsets:
                value = max(offset + late + rng.randint(-20, 60), previous + UNIT)
                actual.append(value)
                previous = value
            columns.append([round(v / UNIT) for v in actual])
        coded = [[None] * len(day_indexes) for _ in stops]
        for c, column in enumerate(columns):
            last = 0
            for k in range(len(stops)):
                if 0 < k < len(stops) - 1 and rng.random() < 0.05:
                    continue
                coded[k][c] = column[k] - last
                last = column[k]
        units = [round(o / UNIT) for o in offsets]
        scheduled = [units[0]] + [units[k] - units[k - 1] for k in range(1, len(units))]
        patterns.append([start, day_indexes, list(range(len(stops))), coded, scheduled])
    return {
        "line": line,
        "direction": direction,
        "day_type": kind,
        "days": days,
        "stops": [s[0] for s in stops],
        "patterns": patterns,
    }


def write_commute(out: Path):
    pointer_path = out / "site" / "current.json"
    pointer = json.loads(pointer_path.read_text())
    run_dir = out / pointer["prefix"]
    folder = run_dir / "commute"
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir()
    rng = random.Random(37)
    entries = []
    all_days: set[str] = set()
    for line, direction, kind, first, count, starts, ran in COMMUTE_FILES:
        doc = commute_file(line, direction, kind, first, count, starts, ran, rng)
        name = f"{line}-{direction}-{kind}.json"
        (folder / name).write_text(json.dumps(doc))
        all_days.update(doc["days"])
        entries.append(
            {
                "line": line,
                "direction": direction,
                "day_type": kind,
                "file": f"commute/{name}",
                "patterns": len(doc["patterns"]),
                "days": count,
            }
        )
    stops = {s[0]: list(s) for by in COMMUTE_STOPS.values() for d in by.values() for s in d}
    (folder / "stops.json").write_text(json.dumps([stops[k] for k in sorted(stops)]))
    days = sorted(all_days)
    index = {
        "first_day": days[0],
        "last_day": days[-1],
        "days": len(days),
        "unit": UNIT,
        "stops": "commute/stops.json",
        "files": entries,
    }
    (folder / "index.json").write_text(json.dumps(index))
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
    write_commute(out)
    write_health(out)


if __name__ == "__main__":
    if sys.argv[1] == "--health":
        write_health(Path(sys.argv[2]))
    elif sys.argv[1] == "--commute":
        write_commute(Path(sys.argv[2]))
    elif sys.argv[1] == "--estimates":
        write_estimates(Path(sys.argv[2]))
    else:
        main(Path(sys.argv[1]), Path(sys.argv[2]))
