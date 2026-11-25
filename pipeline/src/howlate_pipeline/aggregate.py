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

Each stop and direction also carries one all-day set of numbers, so a page can
show "how bad is this stop" without adding up dayparts that may have gaps.
`network.json` holds the hour-of-week shape for the whole network, bus and rail.
`health.json` holds the daily report's results for the newest two weeks.

Trip origins are excluded throughout. They measure a departure rather than an
arrival and mixing the two would quietly bias every number toward "early".
"""

import gzip
import json
import secrets
import shutil
from datetime import UTC, datetime
from pathlib import Path

import duckdb
from google.api_core.exceptions import NotFound, PreconditionFailed
from google.cloud import storage

from howlate_pipeline import DERIVED_BUCKET, ZONE, health
from howlate_pipeline.arrivals import VERSION

# Six parts of the day, three kinds of day. Coarse enough that cells hold real
# numbers, fine enough to still answer "when".
DAYPARTS = [(0, "early"), (6, "am"), (9, "mid"), (15, "pm"), (19, "eve"), (22, "late")]

BUCKET_SQL = f"""
    CASE WHEN dow < 5 THEN 'wk' WHEN dow = 5 THEN 'sa' ELSE 'su' END || '-' ||
    CASE {" ".join(f"WHEN hr >= {h} THEN '{name}'" for h, name in reversed(DAYPARTS))} END
"""


def load(con: duckdb.DuckDBPyConnection, arrivals: Path) -> tuple[str, str, int]:
    """Read every service day collected so far, in local time.

    Everything downstream groups by local wall clock, because "is it bad at 8am"
    means 8am in Los Angeles and nowhere else.
    """
    # Inlined rather than bound: DuckDB will not accept a prepared parameter
    # inside CREATE VIEW. The path is ours, and the quote doubling keeps a
    # directory with an apostrophe in it from ending the string early.
    #
    # One level deep, not "**": pointed at the arrivals root by mistake, a
    # recursive glob would read v1 and v2 of the same day and count it twice.
    # This way the root finds only v1, and a version directory only itself.
    glob = str(arrivals / "service_date=*" / "*.parquet").replace("'", "''")
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


# On time is 60 s early to 300 s late, both ends included. Metro's 2025 Transit
# Service Policies and Standards (section 3.3) call a bus or train on time when
# it is "no more than 1 minute early and no more than 5 minutes late", and use
# the same window for rail. The standard does not say whether exactly 5 minutes
# counts, and "no more than" reads as inclusive. Delays are whole seconds. Over
# all 51.6 million measured arrivals of the 90 service days from 2026-08-18 to
# 2026-11-15, 0.11% sit at exactly -60 s and 0.04% at exactly +300 s, so the
# reading of the edges moves the share by about 0.15 points.
#
# Metro measures bus at timepoints and rail at the end terminal. HowLate scores
# the arrival at every scheduled stop, so the result is not Metro's published
# on-time performance and the schemas say so.
ONTIME_FROM, ONTIME_TO = -60, 300

# Every grain wants the same numbers, and only the grouping differs. Keeping the
# expression in one place means the profile, the stop cells and the headlines
# can never drift into measuring subtly different things. The names are the
# keys of the files, so a row from the query is the entry as written.
SPREAD = """
    count(*) FILTER (WHERE delay_seconds IS NOT NULL)    AS n,
    CAST(round(median(delay_seconds)) AS INTEGER)        AS med,
    CAST(round(quantile_cont(delay_seconds, 0.9)) AS INTEGER) AS p90,
    round(100.0 * count(*) FILTER (WHERE delay_seconds > 300)
          / nullif(count(*) FILTER (WHERE delay_seconds IS NOT NULL), 0), 1) AS pct5
"""
ONTIME = f"""
    round(100.0 * count(*) FILTER (WHERE delay_seconds BETWEEN {ONTIME_FROM} AND {ONTIME_TO})
          / nullif(count(*) FILTER (WHERE delay_seconds IS NOT NULL), 0), 1) AS ontime
"""
# How many of those delays were placed between two reports, because the vehicle
# never reported the stop (source interpolated), and not seen there. They are in
# n, the median and the on-time share like every other delay, so each total that
# carries an n carries this beside it, and a reader can see how much of the
# figure is estimated. Hour and daypart cells do not carry it, to keep the line
# files small: 54 KB of line 92's 70 KB gzipped is its daypart cells.
ESTIMATED = """
    count(*) FILTER (WHERE source = 'interpolated' AND delay_seconds IS NOT NULL) AS est
"""
DELAYS = f"{SPREAD}, {ONTIME}"
METRICS = f"count(*) AS sched, {DELAYS}"
# A daypart cell has no ontime. Of line 92's 70 KB gzipped, its 4,167 cells were
# 54 KB, and an ontime on each added 9.6 KB. The pages read med per daypart.
CELL_METRICS = f"count(*) AS sched, {SPREAD}"


def rows(con: duckdb.DuckDBPyConnection, sql: str) -> list[dict]:
    """Run a query and return each row as a dict keyed by its column names."""
    relation = con.sql(sql)
    return [dict(zip(relation.columns, row, strict=True)) for row in relation.fetchall()]


def profiles(con: duckdb.DuckDBPyConnection) -> dict[tuple, list]:
    """Hour-of-week shape for each line and direction, pooled over all its stops."""
    out = {}
    for row in rows(
        con,
        f"""
        SELECT agency, line, direction_id, how AS h, {METRICS}
        FROM a GROUP BY 1, 2, 3, 4
        HAVING count(*) FILTER (WHERE delay_seconds IS NOT NULL) > 0
        ORDER BY 1, 2, 3, 4
    """,
    ):
        key = (row.pop("agency"), row.pop("line"), row.pop("direction_id"))
        out.setdefault(key, []).append(row)
    return out


def stop_cells(con: duckdb.DuckDBPyConnection) -> dict[tuple, dict]:
    """Per stop, per part of the day, plus where the stop sits along the route.

    Totals are counted over every scheduled stop, dayparts only over the ones
    with something in them. Deriving the totals by summing the cells instead
    would lose the ~62,000 scheduled stops whose daypart saw nothing at all, and
    the file would then claim better coverage than the data supports.

    `all` pools every day and daypart at the stop. The cells leave out a
    daypart with nothing measured, so a stop's cells can have gaps that `all`
    does not. It has no `n`, because the stop's own `n` is the same count. A stop
    with nothing measured has an `n` of 0 and nulls in `all`.
    """
    out = {}
    for row in rows(
        con,
        f"""
        SELECT agency, line, direction_id, stop_id,
               CAST(round(median(stop_sequence)) AS INTEGER) AS seq,
               count(*) AS sched, {DELAYS}, {ESTIMATED}
        FROM a GROUP BY 1, 2, 3, 4 ORDER BY 1, 2, 3, 5, 4
    """,
    ):
        key = (row.pop("agency"), row.pop("line"), row.pop("direction_id"))
        stop = row.pop("stop_id")
        out.setdefault(key, {})[stop] = {
            "seq": row.pop("seq"),
            "n": row.pop("n"),
            "est": row.pop("est"),
            "sched": row.pop("sched"),
            "all": row,
            "cells": [],
        }

    for row in rows(
        con,
        f"""
        SELECT agency, line, direction_id, stop_id, bucket AS d, {CELL_METRICS}
        FROM a GROUP BY 1, 2, 3, 4, 5
        HAVING count(*) FILTER (WHERE delay_seconds IS NOT NULL) > 0
        ORDER BY 1, 2, 3, 4, 5
    """,
    ):
        key = (row.pop("agency"), row.pop("line"), row.pop("direction_id"))
        out[key][row.pop("stop_id")]["cells"].append(row)
    return out


def direction_totals(con: duckdb.DuckDBPyConnection) -> dict[tuple, dict]:
    """The all-day numbers for each line and direction."""
    return {
        (row.pop("agency"), row.pop("line"), row.pop("direction_id")): row
        for row in rows(
            con,
            f"""
            SELECT agency, line, direction_id, {DELAYS}, {ESTIMATED} FROM a GROUP BY 1, 2, 3
            HAVING count(*) FILTER (WHERE delay_seconds IS NOT NULL) > 0
        """,
        )
    }


def headlines(con: duckdb.DuckDBPyConnection) -> dict[tuple, dict]:
    """One row per line for the index, so the homepage needs no other file."""
    return {
        (row.pop("agency"), row.pop("line")): row
        for row in rows(
            con,
            f"""
            SELECT agency, line, {METRICS}, {ESTIMATED} FROM a GROUP BY 1, 2
            HAVING count(*) FILTER (WHERE delay_seconds IS NOT NULL) > 0
            ORDER BY 1, 2
        """,
        )
    }


def network(con: duckdb.DuckDBPyConnection, modes: dict[tuple, str]) -> dict:
    """The whole network, then bus alone and rail alone, each with its hour-of-week shape.

    `modes` is the mode each line is shown under in the index, so a line is
    counted in the same mode everywhere. The hour profile pools every line,
    which is why it needs the arrivals and cannot be built from the line files.
    A mode with nothing measured is present and empty, so a reader never has to
    test for a missing key.
    """
    con.execute(
        "CREATE OR REPLACE TEMP TABLE line_modes(agency VARCHAR, line VARCHAR, mode VARCHAR)"
    )
    con.executemany("INSERT INTO line_modes VALUES (?, ?, ?)", [(*k, v) for k, v in modes.items()])
    # GROUPING SETS gives the whole network (mode is NULL) and each mode in one scan.
    joined = "FROM a JOIN line_modes USING (agency, line)"
    out = {
        scope: {
            "all": {"n": 0, "est": 0, "med": None, "p90": None, "pct5": None, "ontime": None},
            "profile": [],
        }
        for scope in ("network", "bus", "rail")
    }
    for row in rows(
        con,
        f"SELECT mode, {DELAYS}, {ESTIMATED} {joined} "
        "GROUP BY GROUPING SETS ((mode), ()) ORDER BY mode",
    ):
        out[row.pop("mode") or "network"]["all"] = row
    for row in rows(
        con,
        f"""
        SELECT mode, how AS h, {METRICS} {joined}
        GROUP BY GROUPING SETS ((mode, how), (how))
        HAVING count(*) FILTER (WHERE delay_seconds IS NOT NULL) > 0
        ORDER BY mode NULLS FIRST, how
    """,
    ):
        out[row.pop("mode") or "network"]["profile"].append(row)
    return out


def reports_beside(arrivals_dir: Path) -> Path:
    """Where the saved reports sit when the arrivals are at `arrivals_dir`.

    `out/arrivals/v2` has its reports in `out/reports/v2`, the layout `arrivals`
    writes, so a local run finds them without being told.
    """
    return arrivals_dir.parent.parent / "reports" / arrivals_dir.name


def fetch_arrivals(client: storage.Client, dest: Path, reports: Path | None = None) -> int:
    """Download every finished day of this layout version into `dest`.

    A day counts only once its report is in the bucket. The upload puts the
    report last, so a day whose upload died partway has tables and no report,
    and summarising it would publish half a day.

    Empties `dest` first, so it must be a directory only this function writes.
    It replaces what is there because a day regraded in the bucket must not be
    summarised from an old local copy. On Cloud Run every execution starts
    empty anyway, so this is how the summary sees days graded by other runs.

    With `reports`, the newest `health.RECENT_DAYS` finished days' report.json
    files are also downloaded there, emptied first like `dest`. They come from
    the same listing as the tables, so health.json never names a day the rest of
    the site lacks. Each report is about 3 KB, and nothing is written to the bucket.
    """
    if dest.exists():
        shutil.rmtree(dest)
    saved = {
        blob.name.split("/")[2]: blob
        for blob in client.list_blobs(DERIVED_BUCKET, prefix=f"reports/{VERSION}/")
        if blob.name.endswith("/report.json")
    }
    finished = set(saved)
    if reports is not None:
        if reports.exists():
            shutil.rmtree(reports)
        for day in sorted(saved, reverse=True)[: health.RECENT_DAYS]:
            target = reports / day / "report.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            saved[day].download_to_filename(target)
    prefix = f"arrivals/{VERSION}/"
    count = 0
    for blob in client.list_blobs(DERIVED_BUCKET, prefix=prefix):
        if not blob.name.endswith(".parquet"):
            continue
        if blob.name.removeprefix(prefix).split("/")[0] not in finished:
            continue
        target = dest / blob.name.removeprefix(prefix)
        target.parent.mkdir(parents=True, exist_ok=True)
        blob.download_to_filename(target)
        count += 1
    print(f"  fetched {count} file(s) of {len(finished)} finished day(s) from {prefix}")
    return count


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


def build(
    con: duckdb.DuckDBPyConnection,
    catalogue: dict,
    out: Path,
    first: str,
    last: str,
    days: int,
    reports: Path | None = None,
) -> tuple[list[tuple[str, int, int]], list[str]]:
    """Write index.json, status.json, network.json, health.json and one file per line.

    `reports` holds the saved daily reports that health.json is built from. Without
    them the file is still written, with no days in it.

    Returns the size of each line file and the names of every file written,
    relative to `out`. `upload` publishes those names and nothing else.
    """
    profile = profiles(con)
    cells = stop_cells(con)
    totals_by_direction = direction_totals(con)
    heads = headlines(con)

    known = {(agency, line) for agency, line, _ in profile}
    index, written, names = [], [], []

    for agency, line in sorted(known, key=lambda k: (k[0], len(k[1]), k[1])):
        meta = catalogue["lines"].get((agency, line), {"label": line, "via": "", "mode": "bus"})

        payload = {
            "line": line,
            "agency": agency,
            **meta,
            "first_day": first,
            "last_day": last,
            "days": days,
            "directions": [],
        }

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
                {
                    "id": stop_id,
                    "name": catalogue["stops"].get((agency, stop_id), {}).get("name", stop_id),
                    "lat": catalogue["stops"].get((agency, stop_id), {}).get("lat"),
                    "lon": catalogue["stops"].get((agency, stop_id), {}).get("lon"),
                    "seq": record["seq"],
                    "n": record["n"],
                    "est": record["est"],
                    "sched": record["sched"],
                    "all": record["all"],
                    "cells": record["cells"],
                }
                for stop_id, record in sorted(
                    cells.get(key, {}).items(), key=lambda pair: pair[1]["seq"]
                )
            ]
            payload["directions"].append(
                {
                    "id": direction,
                    "to": catalogue["directions"].get((agency, line, direction), ""),
                    "n": sum(s["n"] for s in stops),
                    "sched": sum(s["sched"] for s in stops),
                    "all": totals_by_direction[key],
                    "profile": profile[key],
                    "stops": stops,
                }
            )

        size = write_json(out / "lines" / f"{line}.json", payload)
        names.append(f"lines/{line}.json")
        raw = (out / "lines" / f"{line}.json").read_bytes()
        written.append((line, size, len(gzip.compress(raw))))

        head = heads.get((agency, line), {})
        index.append(
            {
                "line": line,
                "agency": agency,
                **meta,
                **head,
                "to": [d["to"] for d in payload["directions"]],
            }
        )

    write_json(
        out / "index.json", {"first_day": first, "last_day": last, "days": days, "lines": index}
    )
    names.append("index.json")

    totals = con.sql("""
        SELECT count(*), count(*) FILTER (WHERE delay_seconds IS NOT NULL),
               count(DISTINCT line), count(DISTINCT trip_id),
               count(*) FILTER (WHERE source = 'interpolated' AND delay_seconds IS NOT NULL)
        FROM a
    """).fetchone()
    write_json(
        out / "status.json",
        {
            "first_day": first,
            "last_day": last,
            "days": days,
            "scheduled_stops": totals[0],
            "measured_arrivals": totals[1],
            "estimated_arrivals": totals[4],
            "coverage_pct": round(100 * totals[1] / totals[0], 1),
            "lines": totals[2],
            "trips": totals[3],
        },
    )
    names.append("status.json")

    default = {"mode": "bus"}
    modes = {
        (agency, line): catalogue["lines"].get((agency, line), default)["mode"]
        for agency, line in con.sql("SELECT DISTINCT agency, line FROM a").fetchall()
    }
    write_json(out / "network.json", network(con, modes))
    names.append("network.json")

    write_json(out / "health.json", health.document(reports, last, days))
    names.append("health.json")

    return written, sorted(names)


# How many published runs stay in the bucket: the current one and the two
# that were current before it. Anything that read the pointer just before it
# moved then has two more daily runs' time to finish copying the run it chose.
KEEP_RUNS = 3

POINTER = "site/current.json"


def upload(
    client: storage.Client, out: Path, names: list[str], run: str | None = None
) -> tuple[int, str]:
    """Publish these files of the site directory to the derived bucket as one new run.

    `names` is what `build` just wrote. The directory is not listed, because on
    a disk reused between runs it still holds the files of earlier builds, and a
    line Metro dropped would be published again with frozen numbers. Clearing
    the directory in `build` would fix the same case, but only for as long as
    every writer remembers to clear it. A list of names has no such condition.

    Stored here, not served from here. Cloud Storage egress is $0.12/GB with no
    useful free allowance, and it is the one line item in this project that could
    turn a good day of traffic into a real bill. Publishing means copying the
    current run into a CDN, which is a separate step.

    Each run goes under site/runs/<run>/, and only once every file is there does
    site/current.json name it. Writing one object is the only atomic step Cloud
    Storage offers, so a run that dies partway leaves current.json naming the
    last complete run, never a mix of old and new files.
    """
    # The time sorts runs by age; the suffix keeps two runs started in the
    # same second out of each other's files. It is UTC on purpose and names no
    # calendar day, so it stays out of pacific_today, and UTC never repeats an
    # hour when daylight saving ends.
    run = run or f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{secrets.token_hex(3)}"
    prefix = f"site/runs/{run}/"
    bucket = client.bucket(DERIVED_BUCKET)

    for name in sorted(names):
        blob = bucket.blob(prefix + name)
        # Run files never change once written, so a long cache is safe.
        blob.cache_control = "public, max-age=31536000, immutable"
        blob.upload_from_filename(out / name, content_type="application/json")

    keep = point_at(bucket, run, prefix, len(names))
    if keep:
        try:
            prune(client, run, keep)
        except Exception as error:
            # Listing failed. The site is published; the next run prunes.
            print(f"  could not prune old runs: {error!r}")
    return len(names), f"gs://{DERIVED_BUCKET}/{prefix}"


def point_at(bucket: storage.Bucket, run: str, prefix: str, files: int) -> set[str] | None:
    """Make site/current.json name this run, unless it already names a newer one.

    Returns the runs to keep: this one and those current before it, which the
    pointer lists. Only runs that were once current are ever listed, so a run
    that died partway or lost a race never takes the place of one a reader may
    still be copying. Returns None when a newer run is already published.

    Two publishers can overlap, such as the daily job and a manual aggregate.
    Without the check the slower one would move the pointer back to an older
    run. The write is conditional on the pointer not having changed since it
    was read, and a lost race is read again rather than overwritten.
    """
    for _ in range(5):
        try:
            current = bucket.get_blob(POINTER)
            generation, previous = 0, []  # 0 means "only if it does not exist yet"
            if current is not None:
                generation = current.generation
                named = json.loads(current.download_as_text(if_generation_match=generation))
                if named["run"] > run:
                    print(f"  {POINTER} already names {named['run']}; leaving it")
                    return None
                if named["run"] == run:  # a retried write that had landed
                    return {run, *named.get("previous", [])}
                previous = [named["run"], *named.get("previous", [])][: KEEP_RUNS - 1]
            pointer = bucket.blob(POINTER)
            # Short, because this one file is what moves when a run is published.
            pointer.cache_control = "public, max-age=60"
            record = {"run": run, "prefix": prefix, "files": files, "previous": previous}
            pointer.upload_from_string(
                json.dumps(record), content_type="application/json", if_generation_match=generation
            )
            return {run, *previous}
        except (PreconditionFailed, NotFound):
            # Another run moved the pointer after it was read. NotFound is the
            # same race: the generation that was read no longer exists.
            continue
    raise RuntimeError(f"{POINTER} kept changing; gave up publishing {run}")


def prune(client: storage.Client, current: str, keep: set[str]) -> None:
    """Delete every run not in `keep`, and anything else under site/.

    Runs named after the current one are left alone, because another process
    may still be uploading them. "Anything else" is the flat layout from before
    runs existed. A failed delete is printed and left for the next run, because
    the site is already published.
    """
    for blob in client.list_blobs(DERIVED_BUCKET, prefix="site/"):
        if blob.name == POINTER:
            continue
        parts = blob.name.split("/")
        if len(parts) > 3 and parts[1] == "runs" and (parts[2] in keep or parts[2] > current):
            continue
        try:
            blob.delete()
        except Exception as error:
            print(f"  could not delete gs://{DERIVED_BUCKET}/{blob.name}: {error!r}")
