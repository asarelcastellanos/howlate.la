"""Check six real bus commutes three ways: C23 of docs/spec/v0.6.0.md.

Follows the contract for `backfill-vm.sh --script`:

    python <script> --service-date YYYYMMDD --cache DIR --out DIR

It fetches the graded days from gs://howlate-derived like the daily job, builds
the site's commute files with `build_site(upload=False)` into CACHE/site, and
works out each commute in COMMUTES three ways:

1. SQL straight over the graded arrival rows (measured LACMTA rows only);
2. the commute files, summed down each day's column as commute.py documents;
3. the same files decoded with the arithmetic of web/src/lib/commute/file.ts,
   ridetime.ts and answer.ts, ported line by line. It also picks the departure
   pattern, as the page does, and the other two read that pattern.

A commute passes when the three ride times agree to within TOLERANCE seconds
and so do the three 9-in-10 arrival times. Each time in a file is rounded to
10 seconds, so a ride time can differ from the rows by up to 10 seconds.
Writes OUT/commute_check_DAY.json and OUT/commute_check_DAY.txt, prints the
table, and exits 1 when any commute fails. Nothing reaches a bucket except
what the wrapper copies from OUT.
"""

import argparse
import json
import math
import sys
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from howlate_pipeline import BUS_AGENCY, aggregate, arrivals, gtfs  # noqa: E402
from howlate_pipeline import __main__ as cli  # noqa: E402

TOLERANCE = 10
UNIT = 10
MIN_DAYS = 8
DAY_SQL = "regexp_replace(CAST(service_date AS VARCHAR), '-', '', 'g')"
MEASURED = "source NOT IN ('none', 'interpolated')"


class Commute(NamedTuple):
    line: str
    direction: int
    day_type: str
    from_stop: str
    to_stop: str
    arrive_by: int


COMMUTES = [
    Commute("720", 1, "weekday", "16769", "5208", 9 * 60),
    Commute("4", 1, "weekday", "16304", "14391", 10 * 60),
    Commute("2", 1, "weekday", "4661", "16346", 8 * 60 + 30),
    Commute("33", 1, "weekday", "140726", "15305", 9 * 60),
    Commute("70", 0, "weekday", "15715", "665", 17 * 60 + 30),
    Commute("33", 0, "saturday", "5630", "6963", 12 * 60),
]


def js_round(value: float) -> int:
    return math.floor(value + 0.5)


def decode_pattern(raw, days: int, stops: int) -> dict | None:
    """decodePattern in file.ts."""

    def is_int(v) -> bool:
        return isinstance(v, int) and not isinstance(v, bool)

    def ints(v) -> bool:
        return isinstance(v, list) and all(is_int(i) for i in v)

    if not isinstance(raw, list) or len(raw) != 5:
        return None
    start, day_indexes, stop_indexes, rows, scheduled = raw
    if not is_int(start) or start < 0 or not ints(day_indexes) or not ints(stop_indexes):
        return None
    if not isinstance(rows, list) or not ints(scheduled) or len(scheduled) != len(stop_indexes):
        return None
    if any(d < 0 or d >= days for d in day_indexes):
        return None
    if any(s < 0 or s >= stops for s in stop_indexes):
        return None
    if len(rows) != len(stop_indexes):
        return None
    for row in rows:
        if not isinstance(row, list) or len(row) != len(day_indexes):
            return None
        if not all(v is None or is_int(v) for v in row):
            return None
    return {
        "start": start,
        "dayIndexes": day_indexes,
        "stopIndexes": stop_indexes,
        "rows": rows,
        "scheduled": scheduled,
    }


def decode_commute_file(body, line: str, direction: int, day_type: str) -> dict | None:
    """decodeCommuteFile in file.ts."""
    if not isinstance(body, dict):
        return None
    if (body.get("line"), body.get("direction"), body.get("day_type")) != (
        line,
        direction,
        day_type,
    ):
        return None
    days, stops, patterns = body.get("days"), body.get("stops"), body.get("patterns")
    if not isinstance(days, list) or not all(
        isinstance(d, str) and len(d) == 8 and d.isascii() and d.isdigit() for d in days
    ):
        return None
    if not isinstance(stops, list) or not all(isinstance(s, str) for s in stops):
        return None
    if not isinstance(patterns, list):
        return None
    decoded = []
    for raw in patterns:
        pattern = decode_pattern(raw, len(days), len(stops))
        if pattern is None:
            return None
        decoded.append(pattern)
    return {"days": days, "stops": stops, "patterns": decoded}


def column_times(pattern: dict, column: int) -> list[int | None]:
    """columnTimes in ridetime.ts."""
    total = 0
    times: list[int | None] = []
    for row in pattern["rows"]:
        value = row[column]
        if value is None:
            times.append(None)
        else:
            total += value
            times.append(total)
    return times


def ride_times(file: dict, start: int, a_stop: str, b_stop: str) -> list[tuple[str, int]] | None:
    """rideTimes in ridetime.ts. None stands for each of its error results."""
    pattern = next((p for p in file["patterns"] if p["start"] == start), None)
    if pattern is None:
        return None
    order = [file["stops"][i] for i in pattern["stopIndexes"]]
    if a_stop not in order or b_stop not in order:
        return None
    a = order.index(a_stop)
    if b_stop not in order[a + 1 :]:
        return None
    b = order.index(b_stop, a + 1)
    data = []
    for column, day_index in enumerate(pattern["dayIndexes"]):
        times = column_times(pattern, column)
        at_a, at_b = times[a], times[b]
        if at_a is None or at_b is None:
            continue
        data.append((file["days"][day_index], (at_b - at_a) * UNIT))
    return data


def nearest_rank_90(values: list[float]) -> float:
    return sorted(values)[math.ceil(0.9 * len(values)) - 1]


def median(values: list[float]) -> float:
    ordered = sorted(values)
    mid = len(ordered) >> 1
    return ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2


def scheduled_offset(pattern: dict, stop: int) -> int:
    return sum(pattern["scheduled"][: stop + 1]) * UNIT


def positions(file: dict, pattern: dict, from_stop: str, to_stop: str) -> tuple[int, int] | None:
    order = [file["stops"][i] for i in pattern["stopIndexes"]]
    if from_stop not in order:
        return None
    a = order.index(from_stop)
    if to_stop not in order[a + 1 :]:
        return None
    return a, order.index(to_stop, a + 1)


def candidate(file: dict, pattern: dict, from_stop: str, to_stop: str) -> dict | None:
    """candidate in answer.ts."""
    ride = ride_times(file, pattern["start"], from_stop, to_stop)
    if not ride:
        return None
    a, b = positions(file, pattern, from_stop, to_stop)
    at_b = []
    for column in range(len(pattern["dayIndexes"])):
        times = column_times(pattern, column)
        if times[a] is None or times[b] is None:
            continue
        at_b.append(times[b] * UNIT)
    scheduled_a = scheduled_offset(pattern, a)
    scheduled_b = scheduled_offset(pattern, b)
    lates = [t - scheduled_b for t in at_b]
    return {
        "start": pattern["start"],
        "departSeconds": pattern["start"] + scheduled_a,
        "scheduledArriveSeconds": pattern["start"] + scheduled_b,
        "arrive90Minute": math.ceil((pattern["start"] + nearest_rank_90(at_b)) / 60),
        "medianLateSeconds": median(lates),
        "badLateSeconds": nearest_rank_90(lates),
        "rideSeconds": median([seconds for _, seconds in ride]),
        "days": len(at_b),
    }


def arrival_spread(file: dict, start: int, from_stop: str, to_stop: str) -> dict | None:
    """arrivalSpread in answer.ts."""
    pattern = next((p for p in file["patterns"] if p["start"] == start), None)
    if pattern is None:
        return None
    found = positions(file, pattern, from_stop, to_stop)
    if found is None:
        return None
    a, b = found
    arrives = []
    for column in range(len(pattern["dayIndexes"])):
        times = column_times(pattern, column)
        if times[a] is None or times[b] is None:
            continue
        arrives.append(start + times[b] * UNIT)
    if not arrives:
        return None
    return {
        "scheduled": start + scheduled_offset(pattern, b),
        "nineInTen": nearest_rank_90(arrives),
        "arrivals": arrives,
    }


def answer(file: dict, from_stop: str, to_stop: str, minute: int) -> dict:
    """answer in answer.ts, in its 'arrive' mode."""
    found = [c for p in file["patterns"] if (c := candidate(file, p, from_stop, to_stop))]
    fits = [c for c in found if c["arrive90Minute"] <= minute]
    if not fits:
        return {"kind": "no-bus", "candidates": len(found)}
    chosen = sorted(fits, key=lambda c: -c["departSeconds"])[0]
    base = {
        "start": chosen["start"],
        "departMinute": chosen["departSeconds"] // 60,
        "days": chosen["days"],
        "candidates": len(found),
    }
    if chosen["days"] < MIN_DAYS:
        return {"kind": "not-enough-data", **base}
    return {
        "kind": "answer",
        **base,
        "scheduledArriveMinute": chosen["scheduledArriveSeconds"] // 60,
        "nineInTenMinute": chosen["arrive90Minute"],
        "spareMinutes": minute - chosen["arrive90Minute"],
        "rideMinutes": js_round(chosen["rideSeconds"] / 60),
    }


def from_files(body: dict, start: int, from_stop: str, to_stop: str) -> dict:
    """Way 2: sum each day's column down to each stop, as commute.py documents."""
    pattern = next(p for p in body["patterns"] if p[0] == start)
    _, day_indexes, stop_indexes, rows, _ = pattern
    order = [body["stops"][i] for i in stop_indexes]
    a = order.index(from_stop)
    b = order.index(to_stop, a + 1)
    rides, arrives = [], []
    for column in range(len(day_indexes)):
        total, at = 0, {}
        for k, row in enumerate(rows):
            if row[column] is not None:
                total += row[column]
                at[k] = total * UNIT
        if a in at and b in at:
            rides.append(at[b] - at[a])
            arrives.append(start + at[b])
    return {
        "days": len(rides),
        "ride_seconds": median(rides),
        "nine_in_ten_seconds": nearest_rank_90(arrives),
    }


def from_rows(con, graded: Path, commute: Commute, days: list[str], start: int) -> dict:
    """Way 1: SQL over the graded rows of one line, direction and pattern start."""
    con.execute("DROP TABLE IF EXISTS check_days")
    con.execute("CREATE TABLE check_days (service_date VARCHAR, base BIGINT)")
    con.executemany(
        "INSERT INTO check_days VALUES (?, ?)", [(day, int(gtfs.day_base(day))) for day in days]
    )
    ride, arrive, count = con.execute(
        f"""
        WITH r AS (
            SELECT {DAY_SQL} AS day, trip_id, stop_id, stop_sequence,
                   CAST(epoch(scheduled_time) AS BIGINT) AS sched,
                   CAST(epoch(actual_time) AS BIGINT) AS act, {MEASURED} AS measured
            FROM read_parquet(?, hive_partitioning = false)
            WHERE agency = '{BUS_AGENCY}' AND line = ? AND direction_id = ?
        ),
        t AS (
            SELECT r.day, r.trip_id, min(r.sched) - d.base AS start_s, any_value(d.base) AS base
            FROM r JOIN check_days d ON d.service_date = r.day
            GROUP BY r.day, r.trip_id, d.base
        ),
        a AS (
            SELECT r.day, r.trip_id, min(r.stop_sequence) AS seq
            FROM r WHERE r.measured AND r.stop_id = ? GROUP BY ALL
        ),
        b AS (
            SELECT a.day, a.trip_id, min(r.stop_sequence) AS seq
            FROM a JOIN r ON r.day = a.day AND r.trip_id = a.trip_id
            WHERE r.measured AND r.stop_id = ? AND r.stop_sequence > a.seq
            GROUP BY a.day, a.trip_id
        ),
        trip AS (
            SELECT t.day, t.trip_id, t.start_s,
                   min(ra.act - t.base - t.start_s) AS rel_a,
                   min(rb.act - t.base - t.start_s) AS rel_b
            FROM t
            JOIN a ON a.day = t.day AND a.trip_id = t.trip_id
            JOIN b ON b.day = t.day AND b.trip_id = t.trip_id
            JOIN r ra ON ra.day = t.day AND ra.trip_id = t.trip_id
                     AND ra.stop_sequence = a.seq AND ra.measured
            JOIN r rb ON rb.day = t.day AND rb.trip_id = t.trip_id
                     AND rb.stop_sequence = b.seq AND rb.measured
            WHERE t.start_s = ?
            GROUP BY t.day, t.trip_id, t.start_s
        ),
        per_day AS (
            SELECT day, min(rel_a) AS rel_a, min(rel_b) AS rel_b FROM trip GROUP BY day
        )
        SELECT median(rel_b - rel_a),
               list_sort(list(? + rel_b))[CAST(ceil(0.9 * count(*)) AS BIGINT)],
               count(*)
        FROM per_day
        """,
        [
            [str(path) for path in sorted(graded.glob("service_date=*/*.parquet"))],
            commute.line,
            commute.direction,
            commute.from_stop,
            commute.to_stop,
            start,
            start,
        ],
    ).fetchone()
    return {"days": count, "ride_seconds": ride, "nine_in_ten_seconds": arrive}


def clock(seconds: float) -> str:
    whole = int(round(seconds))
    return f"{whole // 3600:02d}:{whole % 3600 // 60:02d}:{whole % 60:02d}"


def check_one(con, graded: Path, site: Path, names: dict, commute: Commute) -> dict:
    result = {
        "line": commute.line,
        "direction": commute.direction,
        "day_type": commute.day_type,
        "from": [commute.from_stop, names.get(commute.from_stop)],
        "to": [commute.to_stop, names.get(commute.to_stop)],
        "arrive_by_minute": commute.arrive_by,
    }
    path = site / "commute" / f"{commute.line}-{commute.direction}-{commute.day_type}.json"
    if not path.exists():
        return {**result, "pass": False, "problem": f"{path.name} was not built"}
    body = json.loads(path.read_text())
    file = decode_commute_file(body, commute.line, commute.direction, commute.day_type)
    if file is None:
        return {**result, "pass": False, "problem": f"{path.name} does not decode"}
    page = answer(file, commute.from_stop, commute.to_stop, commute.arrive_by)
    result["page"] = page
    if page["kind"] == "no-bus":
        return {**result, "pass": False, "problem": "no pattern arrives by the deadline"}
    start = page["start"]
    spread = arrival_spread(file, start, commute.from_stop, commute.to_stop)
    ride = ride_times(file, start, commute.from_stop, commute.to_stop)
    decoded = {
        "days": len(ride),
        "ride_seconds": median([seconds for _, seconds in ride]),
        "nine_in_ten_seconds": spread["nineInTen"],
    }
    ways = {
        "rows": from_rows(con, graded, commute, body["days"], start),
        "files": from_files(body, start, commute.from_stop, commute.to_stop),
        "decoded": decoded,
    }
    rides = [w["ride_seconds"] for w in ways.values()]
    arrives = [w["nine_in_ten_seconds"] for w in ways.values()]
    days = {w["days"] for w in ways.values()}
    return {
        **result,
        "start": start,
        "ways": ways,
        "ride_spread_seconds": max(rides) - min(rides),
        "nine_in_ten_spread_seconds": max(arrives) - min(arrives),
        "pass": max(rides) - min(rides) <= TOLERANCE
        and max(arrives) - min(arrives) <= TOLERANCE
        and len(days) == 1,
    }


def table(results: list[dict]) -> str:
    lines = [
        "commute | stops | ride s rows/files/decoded | 9-in-10 rows/files/decoded | days | page | result"
    ]
    for r in results:
        label = f"{r['line']} dir {r['direction']} {r['day_type']} arrive by {r['arrive_by_minute'] // 60}:{r['arrive_by_minute'] % 60:02d}"
        stops = f"{r['from'][0]} {r['from'][1]} to {r['to'][0]} {r['to'][1]}"
        if "ways" not in r:
            lines.append(f"{label} | {stops} | {r['problem']} | | | | FAIL")
            continue
        w = r["ways"]
        rides = "/".join(f"{w[k]['ride_seconds']:.0f}" for k in ("rows", "files", "decoded"))
        arrives = "/".join(clock(w[k]["nine_in_ten_seconds"]) for k in ("rows", "files", "decoded"))
        days = "/".join(str(w[k]["days"]) for k in ("rows", "files", "decoded"))
        page = r["page"]
        shown = (
            f"{page['kind']}, {page['rideMinutes']} min ride, 9 in 10 at minute {page['nineInTenMinute']}"
            if page["kind"] == "answer"
            else page["kind"]
        )
        verdict = "PASS" if r["pass"] else "FAIL"
        lines.append(f"{label} | {stops} | {rides} | {arrives} | {days} | {shown} | {verdict}")
    return "\n".join(lines)


def check_all(graded: Path, site: Path, commutes: list[Commute]) -> list[dict]:
    names = {
        stop_id: name
        for stop_id, name, _, _ in json.loads((site / "commute" / "stops.json").read_text())
    }
    con = arrivals.connect()
    return [check_one(con, graded, site, names, commute) for commute in commutes]


def run(service_date: str, cache: Path, out: Path) -> int:
    bucket = cli.Bucket()
    graded = cache / "graded" / arrivals.VERSION
    fetched = aggregate.fetch_arrivals(bucket(), graded, aggregate.reports_beside(graded))
    site = cache / "site"
    code = cli.build_site(bucket, graded, cache=cache, out=site, upload=False)
    results = check_all(graded, site, COMMUTES)
    text = table(results)
    print(text)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"commute_check_{service_date}.txt").write_text(text + "\n")
    (out / f"commute_check_{service_date}.json").write_text(
        json.dumps(
            {
                "service_date": service_date,
                "graded_days_fetched": fetched,
                "build_site_exit": code,
                "tolerance_seconds": TOLERANCE,
                "commutes": results,
            },
            indent=2,
        )
        + "\n"
    )
    return 0 if all(r["pass"] for r in results) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--service-date", required=True, help="YYYYMMDD")
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    sys.exit(run(args.service_date, args.cache, args.out))
