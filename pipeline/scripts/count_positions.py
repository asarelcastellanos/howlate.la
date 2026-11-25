"""Count the vehicle position records of one service day, by agency.

This is the smallest script that follows the contract for `backfill-vm.sh
--script`. Every script run that way is called as

    python <script> --service-date YYYYMMDD --cache DIR --out DIR

It reads raw files through `arrivals.fetch_raw`, which is free on the backfill VM
and refused elsewhere, and it writes its results under --out. The VM copies
--out to gs://howlate-derived/logs/scripts/ and clears --cache after each day.
A script never writes to a bucket itself.

Writes OUT/count_positions_DAY.json with the count for each agency. A record
counts when its trip says it belongs to the day, the same test `load_observations`
uses, but without that function's requirement that a trip, stop and time are
present.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from howlate_pipeline import arrivals  # noqa: E402
from howlate_pipeline.__main__ import Bucket  # noqa: E402


def count(service_date: str, cache: Path, out: Path) -> None:
    files = arrivals.fetch_raw(Bucket()(), service_date, cache)
    con = arrivals.connect()
    rows = con.execute(
        f"SELECT agency, count(*) FROM ({arrivals.EXTRACT}) WHERE service_date = ? "
        "GROUP BY agency ORDER BY agency",
        [files, service_date],
    ).fetchall()
    out.mkdir(parents=True, exist_ok=True)
    (out / f"count_positions_{service_date}.json").write_text(
        json.dumps({"service_date": service_date, "positions": dict(rows)}, indent=2) + "\n"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--service-date", required=True, help="YYYYMMDD")
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    count(args.service_date, args.cache, args.out)
