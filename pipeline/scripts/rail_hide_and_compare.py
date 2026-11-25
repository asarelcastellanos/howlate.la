"""Hide the reported id of each trusted rail run, match it by position, and compare.

Run on the backfill VM as

    python pipeline/scripts/rail_hide_and_compare.py --service-date YYYYMMDD --cache DIR --out DIR

or on local files with no bucket access

    python pipeline/scripts/rail_hide_and_compare.py --service-date YYYYMMDD --out DIR \
        --raw-dir RAW --gtfs-dir GTFS_RAIL

where GTFS_RAIL holds the unpacked rail timetable.

A run looks trusted when its reported id is a running trip and its startTime is
within `railmatch.TRUST_START_S` of that trip's first departure. This script
fits each such run to the trips in force without reading the id, as the matcher
does for a run it does not trust, and counts how often the confident fit is the
reported trip. It reports that raw share, and the share with the runs set aside
whose id is a misfit under the rule `rail_misfit_pct` uses (`railmatch.is_misfit`).

Writes OUT/rail_hide_and_compare_DAY.json with one entry per line, and
OUT/rail_hide_and_compare_DAY.csv with one row per run.
"""

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from howlate_pipeline import RAIL_AGENCY, arrivals, gtfs, railmatch  # noqa: E402
from howlate_pipeline.__main__ import Bucket  # noqa: E402


def share(part: int, whole: int) -> float:
    return round(100 * part / whole, 1) if whole else 0.0


def summarise(decided: dict) -> dict:
    """Per line, the runs that look trusted, how many fit confidently, and how many agree."""
    lines: dict[str, dict] = {}
    for group in decided.values():
        for d in group:
            entry = lines.setdefault(
                d.run["route"],
                dict.fromkeys(
                    (
                        "runs",
                        "trusted",
                        "confident",
                        "agree",
                        "misfits",
                        "set_aside",
                        "matched",
                        "ungraded",
                    ),  # fmt: skip
                    0,
                ),
            )
            entry["runs"] += 1
            if d.outcome != "trusted":
                entry[d.outcome] += 1
            if not d.looks_trusted:
                continue
            entry["trusted"] += 1
            entry["misfits"] += d.misfit
            if d.fit["best"] is not None and d.fit["confident"]:
                entry["confident"] += 1
                entry["agree"] += d.fit["best"].trip_id == d.reported
                entry["set_aside"] += d.misfit
    for entry in lines.values():
        entry["agree_pct_raw"] = share(entry["agree"], entry["confident"])
        entry["agree_pct_misfits_set_aside"] = share(
            entry["agree"], entry["confident"] - entry["set_aside"]
        )
    return dict(sorted(lines.items()))


def run_rows(decided: dict, trips: dict) -> list[dict]:
    """One row per run, with what the diagnosis of the misses needs."""
    out = []
    for group in decided.values():
        for d in group:
            fit, best = d.fit, d.fit["best"]
            reported = trips.get(d.reported)
            out.append(
                {
                    "vehicle": d.vehicle,
                    "fitted_route": d.run["route"],
                    "direction": d.run["direction"],
                    "outcome": d.outcome,
                    "looks_trusted": d.looks_trusted,
                    "misfit": d.misfit,
                    "confident": best is not None and fit["confident"],
                    "reported": d.reported,
                    "reported_route": reported.route if reported else None,
                    "fitted": best.trip_id if best else None,
                    "agree": best is not None and best.trip_id == d.reported,
                    "fitted_miss_s": None if best is None else round(fit["miss"]),
                    "second_miss_s": None
                    if best is None or fit["second"] is None
                    else round(fit["second"]),
                    "reported_miss_s": None
                    if d.reported not in fit.get("misses", {})
                    else round(fit["misses"][d.reported]),
                    "offset_min": None
                    if best is None or reported is None
                    else round((reported.first_dep - best.first_dep) / 60, 1),
                }
            )
    return out


def compare(service_date: str, files: list[str], timetable, out: Path) -> None:
    con = arrivals.connect()
    arrivals.load_observations(con, files, service_date)
    directory = timetable(arrivals.observed_trip_ids(con))
    trips, coords, _ = railmatch.load_timetable([directory], service_date)
    routes = railmatch.build_routes(trips, coords)
    rows = con.execute(
        "SELECT DISTINCT vehicle_id, ts, lat, lon, trip_id, start_time, route_id FROM observations "
        "WHERE agency = ? AND vehicle_id IS NOT NULL ORDER BY vehicle_id, ts",
        [RAIL_AGENCY],
    ).fetchall()
    decided = railmatch.decide(rows, trips, routes, int(gtfs.day_base(service_date)))
    lines = summarise(decided)

    out.mkdir(parents=True, exist_ok=True)
    detail = run_rows(decided, trips)
    with (out / f"rail_hide_and_compare_{service_date}.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(detail[0]) if detail else ["none"])
        writer.writeheader()
        writer.writerows(detail)
    (out / f"rail_hide_and_compare_{service_date}.json").write_text(
        json.dumps(
            {"service_date": service_date, "timetable": directory.name, "lines": lines}, indent=2
        )
        + "\n"
    )
    print(f"{service_date}  line trusted confident agree raw%  misfits set_aside agree% set aside")
    for line, e in lines.items():
        print(
            f"{service_date}  {line:>4} {e['trusted']:>7} {e['confident']:>9} {e['agree']:>5} "
            f"{e['agree_pct_raw']:>5}  {e['misfits']:>7} {e['set_aside']:>9} "
            f"{e['agree_pct_misfits_set_aside']:>5}"
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
