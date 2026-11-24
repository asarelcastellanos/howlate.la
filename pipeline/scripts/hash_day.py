"""Grade one day with this checkout's code and hash what it writes. Uploads nothing.

Run on the backfill VM as

    python pipeline/scripts/hash_day.py --service-date YYYYMMDD --cache DIR --out DIR

or on local files with no bucket access

    python pipeline/scripts/hash_day.py --service-date YYYYMMDD --out DIR --cache DIR \
        --raw-dir RAW --gtfs-dir GTFS

where GTFS holds gtfs_bus/ and gtfs_rail/ already unpacked.

Run it from two git refs and compare the two JSON files to prove that a change
leaves a day's graded output as it was. The script imports only what the
v0.5.2 release already has, so it runs unchanged on code from before a change.

Writes OUT/hash_day_DAY.json. For `arrivals` and `trips`, the row count, a hash
of each column and of each whole row, and the rows per `source` and per agency.
Each hash is the sum of DuckDB's `hash` over the rows, so row order does not
matter and two equal days give equal numbers. The graded files go under CACHE,
which the VM clears, so only the JSON is copied out.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from howlate_pipeline import arrivals  # noqa: E402
from howlate_pipeline.__main__ import Bucket, grade_day, local_timetables  # noqa: E402


def summarize(path: Path) -> dict:
    con = duckdb.connect()
    quoted = str(path).replace("'", "''")
    con.execute(f"CREATE VIEW t AS SELECT * FROM read_parquet('{quoted}')")
    columns = [name for name, *_ in con.execute("DESCRIBE t").fetchall()]
    sums = ", ".join(f'sum(hash("{name}")::HUGEINT)::VARCHAR' for name in columns)
    count, row_hash, *hashes = con.execute(
        f"SELECT count(*), sum(hash(t))::HUGEINT::VARCHAR, {sums} FROM t"
    ).fetchone()
    out = {"rows": count, "row_hash": row_hash, "columns": dict(zip(columns, hashes, strict=True))}
    for column in ("source", "agency"):
        if column in columns:
            found = con.execute(
                f'SELECT "{column}", count(*) FROM t GROUP BY ALL ORDER BY 1 NULLS LAST'
            ).fetchall()
            out[f"rows_per_{column}"] = {str(key): n for key, n in found}
    return out


def commit() -> str | None:
    root = Path(__file__).resolve().parents[2]
    try:
        done = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True
        )
    except OSError:
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--service-date", required=True, help="YYYYMMDD")
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--raw-dir", type=Path, help="read raw files from here, no bucket")
    parser.add_argument("--gtfs-dir", type=Path, help="gtfs_bus/ and gtfs_rail/, needs --raw-dir")
    args = parser.parse_args()
    if bool(args.raw_dir) != bool(args.gtfs_dir):
        sys.exit("--raw-dir and --gtfs-dir go together")
    service_date = args.service_date
    timetables = local_timetables(args.gtfs_dir, upload=False) if args.raw_dir else None

    graded = args.cache / "hash_day_graded"
    grade_day(
        Bucket(),
        service_date,
        cache=args.cache,
        out=graded,
        raw_dir=args.raw_dir,
        timetables=timetables,
        upload=False,
    )

    result: dict = {"service_date": service_date}
    sha = commit()
    if sha:
        result["commit"] = sha
    for table in ("arrivals", "trips"):
        result[table] = summarize(
            graded / arrivals.partition(table, service_date) / "part-0.parquet"
        )
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / f"hash_day_{service_date}.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
