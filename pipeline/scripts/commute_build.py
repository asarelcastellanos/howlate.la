"""Run the daily site build, commute files included, over the 56 days ending at --service-date.

Follows the contract for `backfill-vm.sh --script`:

    python <script> --service-date YYYYMMDD --cache DIR --out DIR

It fetches the graded days from gs://howlate-derived like the daily job, calls
`build_site` without uploading, and writes the site under CACHE/site so nothing
reaches a bucket or the site's own prefix. Writes OUT/commute_build_DAY.json with
the number of files, the largest file gzipped, the total size, the wall time of
the commute build and of the whole site build, and the peak resident memory.
"""

import argparse
import gzip
import json
import resource
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from howlate_pipeline import __main__ as cli  # noqa: E402
from howlate_pipeline import aggregate, arrivals, commute  # noqa: E402


def peak_bytes() -> int:
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak if sys.platform == "darwin" else peak * 1024


def run(service_date: str, cache: Path, out: Path) -> None:
    bucket = cli.Bucket()
    graded = cache / "graded" / arrivals.VERSION
    started = time.perf_counter()
    fetched = aggregate.fetch_arrivals(bucket(), graded, aggregate.reports_beside(graded))
    fetch_seconds = time.perf_counter() - started

    spent = {}
    original = commute.build

    def timed(*args, **kwargs):
        begin = time.perf_counter()
        try:
            return original(*args, **kwargs)
        finally:
            spent["commute_build_seconds"] = round(time.perf_counter() - begin, 1)

    commute.build = timed
    site = cache / "site"
    started = time.perf_counter()
    code = cli.build_site(bucket, graded, cache=cache, out=site, upload=False)
    site_seconds = time.perf_counter() - started

    sizes = [
        (path.stat().st_size, len(gzip.compress(path.read_bytes(), 6)))
        for path in sorted((site / "commute").glob("*-*-*.json"))
    ]
    result = {
        "service_date": service_date,
        "graded_days_fetched": fetched,
        "build_site_exit": code,
        "route_files": len(sizes),
        "largest_gzip6": max(g for _, g in sizes),
        "largest_raw": max(r for r, _ in sizes),
        "route_files_total_raw": sum(r for r, _ in sizes),
        "route_files_total_gzip6": sum(g for _, g in sizes),
        "commute_dir_total_raw": sum(p.stat().st_size for p in (site / "commute").iterdir()),
        "stops_json_raw": (site / "commute" / "stops.json").stat().st_size,
        "stops_json_gzip6": len(gzip.compress((site / "commute" / "stops.json").read_bytes(), 6)),
        "limit": commute.LIMIT,
        "fetch_seconds": round(fetch_seconds, 1),
        "site_build_seconds": round(site_seconds, 1),
        **spent,
        "peak_bytes": peak_bytes(),
    }
    out.mkdir(parents=True, exist_ok=True)
    target = out / f"commute_build_{service_date}.json"
    partial = target.with_suffix(".tmp")
    try:
        partial.write_text(json.dumps(result, indent=2) + "\n")
        partial.replace(target)
    finally:
        partial.unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--service-date", required=True, help="YYYYMMDD")
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    run(args.service_date, args.cache, args.out)
