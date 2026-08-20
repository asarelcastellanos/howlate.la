"""Turns a pile of measured arrivals into the small files a browser can fetch.

The arrivals table answers "what happened on Tuesday". A rider asks "is my bus
usually late at 8am", which is a different question and needs a different shape.

**Two grains, because there are two questions.** Fine time resolution and fine
spatial resolution cannot both be had. Measured over real data, a stop-by-hour-of-
week grid gives 2.5 million cells holding an average of 4.9 observations after a
month of collection, and a median over five numbers is noise wearing a decimal
point. So each question gets the resolution it needs and gives up the other:

    "when is this line worst?"   hour of week, pooled across every stop
    "how bad is my stop?"        per stop, pooled into six dayparts

Every cell carries what was measured *and* what was scheduled. Only about half of
all scheduled stops can be observed at all, so a cell built on three sightings
must not be able to masquerade as one built on three hundred.

Trip origins are excluded throughout. They measure a departure rather than an
arrival and mixing the two would quietly bias every number toward "early".
"""

import gzip
import json
from pathlib import Path

import duckdb
from google.cloud import storage

from howlate_pipeline import DERIVED_BUCKET, ZONE, labels

# Six parts of the day, three kinds of day. Coarse enough that cells hold real
# numbers, fine enough to still answer "when".
DAYPARTS = [(0, "early"), (6, "am"), (9, "mid"), (15, "pm"), (19, "eve"), (22, "late")]

BUCKET_SQL = f"""
    CASE WHEN dow < 5 THEN 'wk' WHEN dow = 5 THEN 'sa' ELSE 'su' END || '-' ||
    CASE {' '.join(f"WHEN hr >= {h} THEN '{name}'" for h, name in reversed(DAYPARTS))} END
"""


def load(con: duckdb.DuckDBPyConnection, arrivals: Path) -> tuple[str, str, int]:
    """Read every service day collected so far, in local time.

    Everything downstream groups by local wall clock, because "is it bad at 8am"
    means 8am in Los Angeles and nowhere else.
    """
    # Inlined rather than bound: DuckDB will not accept a prepared parameter
    # inside CREATE VIEW. The path is ours, and the quote doubling keeps a
    # directory with an apostrophe in it from ending the string early.
    glob = str(arrivals / "**" / "*.parquet").replace("'", "''")
    con.execute(f"""
        CREATE OR REPLACE VIEW a AS
        SELECT *,
               isodow(scheduled_time AT TIME ZONE '{ZONE}') - 1        AS dow,
               hour(scheduled_time AT TIME ZONE '{ZONE}')             AS hr,
               (isodow(scheduled_time AT TIME ZONE '{ZONE}') - 1) * 24
                 + hour(scheduled_time AT TIME ZONE '{ZONE}')          AS how,
               {BUCKET_SQL} AS bucket
        FROM read_parquet('{glob}')
        WHERE NOT is_origin
    """)

    first, last, days = con.sql(
        "SELECT min(service_date), max(service_date), count(DISTINCT service_date) FROM a"
    ).fetchone()
    return str(first), str(last), days


# Both grains want the same numbers, and only the grouping differs. Keeping the
# expression in one place means the profile and the stop cells can never drift
# into measuring subtly different things.
METRICS = """
    count(*)                                            AS scheduled,
    count(*) FILTER (WHERE delay_seconds IS NOT NULL)    AS measured,
    CAST(round(median(delay_seconds)) AS INTEGER)        AS med,
    CAST(round(quantile_cont(delay_seconds, 0.9)) AS INTEGER) AS p90,
    round(100.0 * count(*) FILTER (WHERE delay_seconds > 300)
          / nullif(count(*) FILTER (WHERE delay_seconds IS NOT NULL), 0), 1) AS pct5
"""


def profiles(con: duckdb.DuckDBPyConnection) -> dict[tuple, list]:
    """Hour-of-week shape for each line and direction, pooled over all its stops."""
    out = {}
    for agency, line, direction, how, sched, n, med, p90, pct5 in con.sql(f"""
        SELECT agency, line, direction_id, how, {METRICS}
        FROM a GROUP BY 1, 2, 3, 4
        HAVING count(*) FILTER (WHERE delay_seconds IS NOT NULL) > 0
        ORDER BY 1, 2, 3, 4
    """).fetchall():
        out.setdefault((agency, line, direction), []).append(
            {"h": how, "n": n, "sched": sched, "med": med, "p90": p90, "pct5": pct5}
        )
    return out


def stop_cells(con: duckdb.DuckDBPyConnection) -> dict[tuple, dict]:
    """Per stop, per part of the day, plus where the stop sits along the route.

    Totals are counted over every scheduled stop, dayparts only over the ones
    with something in them. Deriving the totals by summing the cells instead
    would lose the ~62,000 scheduled stops whose daypart saw nothing at all, and
    the file would then claim better coverage than the data supports.
    """
    out = {}
    for agency, line, direction, stop, seq, sched, n in con.sql("""
        SELECT agency, line, direction_id, stop_id,
               CAST(round(median(stop_sequence)) AS INTEGER) AS seq,
               count(*) AS scheduled,
               count(*) FILTER (WHERE delay_seconds IS NOT NULL) AS measured
        FROM a GROUP BY 1, 2, 3, 4 ORDER BY 1, 2, 3, 5, 4
    """).fetchall():
        out.setdefault((agency, line, direction), {})[stop] = {
            "seq": seq, "n": n, "sched": sched, "cells": []
        }

    for agency, line, direction, stop, bucket, sched, n, med, p90, pct5 in con.sql(f"""
        SELECT agency, line, direction_id, stop_id, bucket, {METRICS}
        FROM a GROUP BY 1, 2, 3, 4, 5
        HAVING count(*) FILTER (WHERE delay_seconds IS NOT NULL) > 0
        ORDER BY 1, 2, 3, 4, 5
    """).fetchall():
        out[(agency, line, direction)][stop]["cells"].append(
            {"d": bucket, "n": n, "sched": sched, "med": med, "p90": p90, "pct5": pct5}
        )
    return out


def headlines(con: duckdb.DuckDBPyConnection) -> dict[tuple, dict]:
    """One row per line for the index, so the homepage needs no other file."""
    return {
        (agency, line): {"n": n, "sched": sched, "med": med, "p90": p90, "pct5": pct5}
        for agency, line, sched, n, med, p90, pct5 in con.sql(f"""
            SELECT agency, line, {METRICS} FROM a GROUP BY 1, 2
            HAVING count(*) FILTER (WHERE delay_seconds IS NOT NULL) > 0
            ORDER BY 1, 2
        """).fetchall()
    }


def write_json(path: Path, payload: dict) -> int:
    """Write one file, deterministically.

    Sorted keys and no wall-clock stamp anywhere, so rerunning over unchanged
    input produces byte-identical output. The freshness signal the site should
    show is the last day of data, not the moment a job happened to run.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    path.write_bytes(body)
    return len(body)


def build(con: duckdb.DuckDBPyConnection, catalogue: dict, out: Path,
          first: str, last: str, days: int) -> list[tuple[str, int, int]]:
    """Write index.json, status.json and one file per line."""
    profile = profiles(con)
    cells = stop_cells(con)
    heads = headlines(con)

    known = {(agency, line) for agency, line, _ in profile}
    index, written = [], []

    for agency, line in sorted(known, key=lambda k: (k[0], len(k[1]), k[1])):
        meta = catalogue["lines"].get((agency, line), {"label": line, "via": "", "mode": "bus"})

        payload = {"line": line, "agency": agency, **meta,
                   "first_day": first, "last_day": last, "days": days, "directions": []}

        for direction in (0, 1):
            key = (agency, line, direction)
            if key not in profile:
                continue
            # Cells with nothing measured are left out to keep the file small,
            # so each stop carries its own totals. Without them a daypart that
            # ran but was never observed would be indistinguishable from one
            # where no bus was scheduled, and the site would quietly overstate
            # how much of the timetable it has actually checked.
            stops = [
                {"id": stop_id,
                 "name": catalogue["stops"].get((agency, stop_id), {}).get("name", stop_id),
                 "lat": catalogue["stops"].get((agency, stop_id), {}).get("lat"),
                 "lon": catalogue["stops"].get((agency, stop_id), {}).get("lon"),
                 "seq": record["seq"],
                 "n": record["n"], "sched": record["sched"],
                 "cells": record["cells"]}
                for stop_id, record in sorted(cells.get(key, {}).items(),
                                              key=lambda pair: pair[1]["seq"])
            ]
            payload["directions"].append({
                "id": direction,
                "to": catalogue["directions"].get((agency, line, direction), ""),
                "n": sum(s["n"] for s in stops),
                "sched": sum(s["sched"] for s in stops),
                "profile": profile[key],
                "stops": stops,
            })

        size = write_json(out / "lines" / f"{line}.json", payload)
        raw = (out / "lines" / f"{line}.json").read_bytes()
        written.append((line, size, len(gzip.compress(raw))))

        head = heads.get((agency, line), {})
        index.append({"line": line, "agency": agency, **meta, **head,
                      "to": [d["to"] for d in payload["directions"]]})

    write_json(out / "index.json", {"first_day": first, "last_day": last,
                                    "days": days, "lines": index})

    totals = con.sql("""
        SELECT count(*), count(*) FILTER (WHERE delay_seconds IS NOT NULL),
               count(DISTINCT line), count(DISTINCT trip_id)
        FROM a
    """).fetchone()
    write_json(out / "status.json", {
        "first_day": first, "last_day": last, "days": days,
        "scheduled_stops": totals[0], "measured_arrivals": totals[1],
        "coverage_pct": round(100 * totals[1] / totals[0], 1),
        "lines": totals[2], "trips": totals[3],
    })

    return written


def upload(client: storage.Client, out: Path) -> tuple[int, str]:
    """Put the whole site directory in the derived bucket, replacing what was there.

    Stored here, not served from here. Cloud Storage egress is $0.12/GB with no
    useful free allowance, and it is the one line item in this project that could
    turn a good day of traffic into a real bill. Publishing means copying this
    directory into a CDN, which is a separate step.

    Files that no longer exist locally are deleted, so a line Metro drops stops
    being served rather than lingering with numbers that never move again.
    """
    bucket = client.bucket(DERIVED_BUCKET)
    local = {path.relative_to(out).as_posix(): path for path in out.rglob("*.json")}

    for stale in client.list_blobs(DERIVED_BUCKET, prefix="site/"):
        if stale.name.removeprefix("site/") not in local:
            stale.delete()

    for name, path in sorted(local.items()):
        blob = bucket.blob(f"site/{name}")
        # An hour: long enough that a burst of readers costs nothing, short
        # enough that a corrected day is visible the same morning.
        blob.cache_control = "public, max-age=3600"
        blob.upload_from_filename(path, content_type="application/json")

    return len(local), f"gs://{DERIVED_BUCKET}/site/"
