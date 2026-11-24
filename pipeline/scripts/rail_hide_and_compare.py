"""Hide the reported id of each trusted rail run, match it by position, and compare.

Run on the backfill VM as

    python pipeline/scripts/rail_hide_and_compare.py --service-date YYYYMMDD --cache DIR --out DIR

or on local files with no bucket access

    python pipeline/scripts/rail_hide_and_compare.py --service-date YYYYMMDD --out DIR \
        --raw-dir RAW --gtfs-dir GTFS_RAIL

where GTFS_RAIL holds the unpacked rail timetable.

A trusted run is one whose reported id is a running trip and whose startTime is
within `railmatch.TRUST_START_S` of that trip's first departure. Its id is known
good on the days when the feed is healthy. This script fits the same run to the
trips in force without reading the id, as the matcher does for a run it does not
trust, and counts how often the confident fit is the reported trip.

Writes OUT/rail_hide_and_compare_DAY.json with one entry per line.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from howlate_pipeline import RAIL_AGENCY, arrivals, gtfs, railmatch  # noqa: E402
from howlate_pipeline.__main__ import Bucket  # noqa: E402


def share(part: int, whole: int) -> float:
    return round(100 * part / whole, 1) if whole else 0.0


def summarise(decided: dict) -> dict:
    """Per line, the trusted runs, how many fit confidently, and how many of those agree."""
    lines: dict[str, dict] = {}
    for group in decided.values():
        for d in group:
            entry = lines.setdefault(
                d.run["route"],
                {"runs": 0, "trusted": 0, "confident": 0, "agree": 0, "matched": 0, "ungraded": 0},
            )
            entry["runs"] += 1
            if d.outcome != "trusted":
                entry[d.outcome] += 1
                continue
            entry["trusted"] += 1
            if d.fit["best"] is not None and d.fit["confident"]:
                entry["confident"] += 1
                entry["agree"] += d.fit["best"].trip_id == d.reported
    for entry in lines.values():
        entry["confident_pct_of_trusted"] = share(entry["confident"], entry["trusted"])
        entry["agree_pct_of_confident"] = share(entry["agree"], entry["confident"])
    return dict(sorted(lines.items()))


def compare(service_date: str, files: list[str], timetable, out: Path) -> None:
    con = arrivals.connect()
    arrivals.load_observations(con, files, service_date)
    directory = timetable(arrivals.observed_trip_ids(con))
    trips, coords, _ = railmatch.load_timetable([directory], service_date)
    routes = railmatch.build_routes(trips, coords)
    rows = con.execute(
        "SELECT DISTINCT vehicle_id, ts, lat, lon, trip_id, start_time FROM observations "
        "WHERE agency = ? AND vehicle_id IS NOT NULL ORDER BY vehicle_id, ts",
        [RAIL_AGENCY],
    ).fetchall()
    decided = railmatch.decide(rows, trips, routes, int(gtfs.day_base(service_date)))
    lines = summarise(decided)

    out.mkdir(parents=True, exist_ok=True)
    (out / f"rail_hide_and_compare_{service_date}.json").write_text(
        json.dumps(
            {"service_date": service_date, "timetable": directory.name, "lines": lines}, indent=2
        )
        + "\n"
    )
    print(f"{service_date}  line  runs trusted confident agree  agree% of confident")
    for line, e in lines.items():
        print(
            f"{service_date}  {line:>4} {e['runs']:>5} {e['trusted']:>7} {e['confident']:>9} "
            f"{e['agree']:>5}  {e['agree_pct_of_confident']:>5}%"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--service-date", required=True, help="YYYYMMDD")
    parser.add_argument("--cache", type=Path, help="raw file cache, required without --raw-dir")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--raw-dir", type=Path, help="read raw files from here, no bucket")
    parser.add_argument("--gtfs-dir", type=Path, help="an unpacked rail timetable, needs --raw-dir")
    args = parser.parse_args()

    if args.raw_dir:
        if not args.gtfs_dir:
            sys.exit("--raw-dir needs --gtfs-dir")
        files = arrivals.local_files(args.raw_dir, args.service_date)

        def timetable(_):
            return args.gtfs_dir

    else:
        if not args.cache or args.gtfs_dir:
            sys.exit("without --raw-dir, give --cache and no --gtfs-dir")
        client = Bucket()()
        files = arrivals.fetch_raw(client, args.service_date, args.cache)

        def timetable(observed):
            return gtfs.prepare(client, args.service_date, args.cache / "gtfs", observed)[
                RAIL_AGENCY
            ]

    if not files:
        sys.exit(f"no raw files found for {args.service_date}")
    compare(args.service_date, files, timetable, args.out)


if __name__ == "__main__":
    main()
