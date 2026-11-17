"""Builds web/e2e/fixture/ from a full `aggregate` output folder.

    python3 web/e2e/make_fixture.py <site folder with index.json, status.json,
        network.json and lines/> web/e2e/fixture
    cd web && npx prettier --write e2e/fixture

The result is trimmed, so its totals do not match the full data. See README.md.
"""

import json
import shutil
import sys
from pathlib import Path

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
    pointer = {"run": RUN, "prefix": f"site/runs/{RUN}/", "files": len(kept) + 3, "previous": []}
    (out / "site" / "current.json").write_text(json.dumps(pointer))


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
