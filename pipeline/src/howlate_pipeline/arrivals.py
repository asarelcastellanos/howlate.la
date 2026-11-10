"""Matches what the vehicles did against what the timetable said they would.

Produces one row per scheduled stop, whether or not anything was seen there.
Rows with no observation are kept deliberately: a stop nobody watched is a fact
about the day, and dropping it would quietly turn 881,000 scheduled stops into
433,000 and make coverage impossible to measure afterwards.

Three things here are not obvious and all three were measured, not assumed.

**The service day is not the UTC day.** Reading only dt=2026-08-18 finds 19.8M
records for that service day. Adding dt=2026-08-19 finds 27.9M. Nearly a third of
every day sits in the next partition, so three partitions are read and the
service date on each record decides what it belongs to.

**The first stop of a trip is a layover, not an arrival.** 86% of observations at
stop_sequence 1 look more than five minutes early, against 0.4% everywhere else.
That is a bus parked at its terminal announcing the trip it has not started. The
first STOPPED_AT there is when it arrived to wait; the last one is when it left.
So the origin is measured as a departure and marked as one.

**The last stop of a trip is never observed.** Not once in 14,340 trips. Vehicles
stop reporting a trip before finishing it. Nothing here can fix that; the rows
exist, unobserved, and the report asserts the count stays at zero so that a
change in the feed's behaviour shows up as a surprise rather than as data.
"""

import glob as globlib
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

import duckdb
from google.cloud import storage

from howlate_pipeline import DERIVED_BUCKET, RAW_BUCKET, gtfs

POSITIONS = "vehicle_positions"

# Every field the analysis needs, pulled out of Metro's message by path rather
# than by letting the reader infer a schema. The payload has optional members
# (bearing appears only when the vehicle is moving) and inference across 43
# million records would be both slower and free to change shape between days.
EXTRACT = """
SELECT
  json_extract_string(j, '$.agency')                           AS agency,
  json_extract_string(j, '$.payload.vehicle.trip.startDate')   AS service_date,
  json_extract_string(j, '$.payload.vehicle.trip.tripId')      AS trip_id,
  json_extract_string(j, '$.payload.vehicle.currentStatus')    AS status,
  CAST(json_extract_string(j, '$.payload.vehicle.currentStopSequence') AS INTEGER) AS stop_sequence,
  json_extract_string(j, '$.payload.vehicle.stopId')           AS stop_id,
  json_extract_string(j, '$.payload.vehicle.vehicle.id')       AS vehicle_id,
  CAST(json_extract_string(j, '$.payload.vehicle.timestamp') AS BIGINT) AS ts
FROM read_json_objects(?) t(j)
"""


def connect() -> duckdb.DuckDBPyConnection:
    """A connection that knows how to read a GTFS clock.

    GTFS writes times as an offset from the service day rather than as a wall
    clock, and lets them run past 24:00:00 so a trip that leaves at half past
    midnight belongs to the day it started. Parsing it as a time would either
    fail on "25:30:00" or, worse, quietly wrap it to 01:30 and move a late-night
    trip to the wrong end of the day.
    """
    con = duckdb.connect()
    # On Cloud Run the disk is memory, shared with the raw cache, so DuckDB's
    # own share and where it spills are set from the job, not left at 80% of
    # the whole limit.
    if limit := os.environ.get("HOWLATE_DUCKDB_MEMORY_LIMIT"):
        con.execute(f"SET memory_limit = '{limit}'")
    if spill := os.environ.get("HOWLATE_DUCKDB_TEMP_DIRECTORY"):
        con.execute(f"SET temp_directory = '{spill}'")
    con.execute("""
        CREATE OR REPLACE MACRO epoch_offset(t) AS
            CAST(split_part(t, ':', 1) AS BIGINT) * 3600
          + CAST(split_part(t, ':', 2) AS BIGINT) * 60
          + CAST(split_part(t, ':', 3) AS BIGINT)
    """)
    return con


def partitions(service_date: str) -> list[str]:
    """The UTC partitions that can hold a local service day: the day either side.

    Generous on purpose. Reading a partition that turns out to hold nothing for
    this service date costs a few seconds; missing one loses an evening without
    saying so.
    """
    day = datetime.strptime(service_date, "%Y%m%d")
    return [(day + timedelta(days=offset)).strftime("%Y-%m-%d") for offset in (-1, 0, 1)]


def fetch_raw(client: storage.Client, service_date: str, cache: Path) -> list[str]:
    """Download the raw files for the window, skipping any already held.

    Objects are immutable once written, so a name already on disk is the right
    contents and never needs re-fetching. That makes a rerun of the same day cost
    nothing and makes iterating on the SQL bearable.
    """
    wanted = []
    for date in partitions(service_date):
        for blob in client.list_blobs(RAW_BUCKET, prefix=f"{POSITIONS}/dt={date}/"):
            wanted.append(blob)

    missing = [b for b in wanted if not (cache / b.name).exists()]
    print(
        f"  raw: {len(wanted)} files across {len(partitions(service_date))} partitions, "
        f"{len(missing)} to download"
    )

    def pull(blob: storage.Blob) -> None:
        target = cache / blob.name
        target.parent.mkdir(parents=True, exist_ok=True)
        # Write beside the target and rename, so an interrupted run cannot leave
        # a half-written file that the next run trusts because the name exists.
        partial = target.with_suffix(".partial")
        blob.download_to_filename(partial)
        partial.rename(target)

    if missing:
        with ThreadPoolExecutor(max_workers=16) as pool:
            list(pool.map(pull, missing))

    return [str(cache / b.name) for b in wanted]


def local_files(directory: Path, service_date: str) -> list[str]:
    """The same window, from a directory already holding the archive's layout.

    Matches only the three dt= partitions. A looser glob that swept up whatever
    .jsonl.gz it found would still produce a correct answer, because records
    carry their own service date, but it would read the entire archive to do it
    and get slower every day the collector runs.
    """
    found = []
    for date in partitions(service_date):
        found += globlib.glob(str(directory / f"**/dt={date}/**/*.jsonl.gz"), recursive=True)
    return sorted(set(found))


def load_observations(con: duckdb.DuckDBPyConnection, files: list[str], service_date: str) -> None:
    """Every position report belonging to this service day.

    Filtered while reading rather than after. Three partitions hold about 43
    million records and only two thirds of them belong to the day being
    measured, so materialising the lot first would cost memory to hold rows that
    are about to be thrown away.
    """
    con.execute(
        f"""
        CREATE OR REPLACE TABLE observations AS
        SELECT * FROM ({EXTRACT}) WHERE service_date = ?
          AND trip_id IS NOT NULL AND stop_sequence IS NOT NULL AND ts IS NOT NULL
    """,
        [files, service_date],
    )


def load_schedule(
    con: duckdb.DuckDBPyConnection, directories: dict[str, Path], service_date: str
) -> None:
    """Every stop every running trip was scheduled to make, from both feeds."""
    base = gtfs.day_base(service_date)

    con.execute(
        "CREATE OR REPLACE TABLE scheduled (agency VARCHAR, line VARCHAR, "
        "route_id VARCHAR, direction_id INTEGER, trip_id VARCHAR, stop_id VARCHAR, "
        "stop_sequence INTEGER, scheduled_arrival BIGINT, scheduled_departure BIGINT, "
        "is_origin BOOLEAN, is_terminus BOOLEAN)"
    )

    for agency, directory in directories.items():
        services = sorted(gtfs.active_services(directory, service_date))
        con.execute(
            "CREATE OR REPLACE TEMP TABLE active AS SELECT unnest(?) AS service_id", [services]
        )

        # GTFS times run past 24:00:00 for trips that cross midnight, so they are
        # read as an offset from the day's base instant and never as a clock.
        con.execute(
            f"""
            INSERT INTO scheduled
            WITH stops AS (
                SELECT
                  t.route_id,
                  CAST(t.direction_id AS INTEGER) AS direction_id,
                  st.trip_id,
                  st.stop_id,
                  CAST(st.stop_sequence AS INTEGER) AS stop_sequence,
                  {base} + epoch_offset(st.arrival_time)   AS scheduled_arrival,
                  {base} + epoch_offset(st.departure_time) AS scheduled_departure
                FROM read_csv(?, all_varchar = true) st
                JOIN read_csv(?, all_varchar = true) t USING (trip_id)
                JOIN active a ON a.service_id = t.service_id
            )
            SELECT
              ? AS agency,
              split_part(route_id, '-', 1) AS line,
              route_id, direction_id, trip_id, stop_id, stop_sequence,
              scheduled_arrival, scheduled_departure,
              stop_sequence = min(stop_sequence) OVER (PARTITION BY trip_id) AS is_origin,
              stop_sequence = max(stop_sequence) OVER (PARTITION BY trip_id) AS is_terminus
            FROM stops
        """,
            [str(directory / "stop_times.txt"), str(directory / "trips.txt"), agency],
        )


def match(con: duckdb.DuckDBPyConnection, service_date: str) -> None:
    """Join the two, and work out how late each vehicle was.

    Mid-route the arrival is the FIRST time the vehicle said it was stopped
    there; a bus that dwells reports the same stop repeatedly and the rider cares
    when it pulled in. At the origin it is the LAST, because that is departure,
    and the vehicle has been sitting there announcing the trip since long before.

    Where the vehicle never said it stopped, the last moment it said it was
    heading there is used instead, and marked `approach`. Only about half of all
    scheduled stops produce a STOPPED_AT, because a bus with nobody waiting rolls
    straight past and has nothing to report, so throwing those away would discard
    a fifth of the network's arrivals for no reason.

    That estimator was checked against 42,313 stops where a real STOPPED_AT also
    existed, so its answer could be compared with the truth: median error **+7
    seconds**, p90 +26s, 90.5% inside half a minute.

    The +7s bias is deliberately left uncorrected. It was measured on stops where
    the bus actually stopped, and these are stops where it did not, so the
    correction cannot be shown to apply. `source` records which rows these are,
    which leaves the choice open to anyone who later measures it properly.

    Origins are excluded from this. The last approach to stop 1 is the vehicle
    arriving at the terminal to wait, which is not the departure being measured.
    """
    con.execute("""
        CREATE OR REPLACE TABLE observed AS
        -- Each vehicle's own story at each stop first, so that a vehicle and
        -- the times credited to it always come from the same bus. A trip can
        -- be claimed by two vehicles at once, or swap vehicles at a stop.
        WITH per_vehicle AS (
            SELECT
              agency, trip_id, stop_sequence, vehicle_id,
              min(ts) FILTER (WHERE status = 'STOPPED_AT')    AS first_stopped,
              max(ts) FILTER (WHERE status = 'STOPPED_AT')    AS last_stopped,
              max(ts) FILTER (WHERE status = 'IN_TRANSIT_TO') AS last_approach
            FROM observations
            GROUP BY agency, trip_id, stop_sequence, vehicle_id
        ),
        chosen AS (
            -- The _null variants keep a report with no vehicle id in the
            -- running, so a missing id shows up as a missing id rather than
            -- as another vehicle's. Same-second ties go by id: the lowest for
            -- a first report, the highest for a last one.
            SELECT
              agency, trip_id, stop_sequence,
              min(first_stopped)  AS first_stopped,
              max(last_stopped)   AS last_stopped,
              max(last_approach)  AS last_approach,
              arg_min_null(vehicle_id, {'t': first_stopped, 'v': vehicle_id})
                FILTER (WHERE first_stopped IS NOT NULL) AS first_stopped_vehicle,
              -- When the vehicle that arrived first left: its own last
              -- STOPPED_AT, not the last one by any vehicle.
              arg_min_null(last_stopped, {'t': first_stopped, 'v': vehicle_id})
                FILTER (WHERE first_stopped IS NOT NULL) AS first_vehicle_left,
              arg_max_null(vehicle_id, {'t': last_stopped, 'v': vehicle_id})
                FILTER (WHERE last_stopped IS NOT NULL)  AS last_stopped_vehicle,
              arg_max_null(vehicle_id, {'t': last_approach, 'v': vehicle_id})
                FILTER (WHERE last_approach IS NOT NULL) AS last_approach_vehicle
            FROM per_vehicle
            GROUP BY agency, trip_id, stop_sequence
        ),
        reported AS (
            SELECT
              agency, trip_id, stop_sequence,
              count(*) FILTER (WHERE status = 'IN_TRANSIT_TO') > 0 AS in_transit_seen,
              count(DISTINCT stop_id) AS distinct_stop_ids,
              -- min, not any_value: any_value differs between runs when a
              -- stop reported two stop_ids, and report.py compares this.
              min(stop_id)            AS reported_stop_id
            FROM observations
            GROUP BY agency, trip_id, stop_sequence
        )
        SELECT * FROM chosen JOIN reported USING (agency, trip_id, stop_sequence)
    """)

    con.execute(f"""
        CREATE OR REPLACE TABLE arrivals AS
        SELECT
          DATE '{service_date[:4]}-{service_date[4:6]}-{service_date[6:]}' AS service_date,
          s.agency, s.line, s.route_id, s.direction_id, s.trip_id,
          s.stop_id, s.stop_sequence,
          to_timestamp(s.scheduled_arrival)   AS scheduled_time,
          CASE
            WHEN s.is_origin THEN to_timestamp(o.last_stopped)
            WHEN o.first_stopped IS NOT NULL THEN to_timestamp(o.first_stopped)
            ELSE to_timestamp(o.last_approach)
          END AS actual_time,
          CASE
            WHEN s.is_origin AND o.last_stopped IS NOT NULL
              THEN CAST(o.last_stopped - s.scheduled_departure AS INTEGER)
            WHEN NOT s.is_origin AND o.first_stopped IS NOT NULL
              THEN CAST(o.first_stopped - s.scheduled_arrival AS INTEGER)
            WHEN NOT s.is_origin AND o.last_approach IS NOT NULL
              THEN CAST(o.last_approach - s.scheduled_arrival AS INTEGER)
          END AS delay_seconds,
          CASE
            WHEN s.is_origin AND o.last_stopped IS NOT NULL      THEN 'origin_departure'
            WHEN NOT s.is_origin AND o.first_stopped IS NOT NULL THEN 'stopped_at'
            WHEN NOT s.is_origin AND o.last_approach IS NOT NULL THEN 'approach'
            ELSE 'none'
          END AS source,
          -- The vehicle whose report set actual_time. A trip can change
          -- vehicles partway, so this can differ from stop to stop.
          CASE
            WHEN s.is_origin THEN o.last_stopped_vehicle
            WHEN o.first_stopped IS NOT NULL THEN o.first_stopped_vehicle
            ELSE o.last_approach_vehicle
          END AS vehicle_id,
          -- When that same vehicle left: its own last STOPPED_AT there. At
          -- the origin that is the departure already measured. Empty when it
          -- never reported stopping, which is about half of all stops.
          -- Mid-route with no vehicle id there is no way to tell one id-less
          -- bus from another, so the departure is left empty rather than
          -- guessed.
          to_timestamp(CASE
            WHEN s.is_origin THEN o.last_stopped
            WHEN o.first_stopped_vehicle IS NULL THEN NULL
            ELSE o.first_vehicle_left
          END) AS departure_time,
          coalesce(o.in_transit_seen, false) AS in_transit_seen,
          s.is_origin, s.is_terminus,
          o.reported_stop_id,
          o.distinct_stop_ids
        FROM scheduled s
        LEFT JOIN observed o
          ON  o.agency = s.agency
          AND o.trip_id = s.trip_id
          AND o.stop_sequence = s.stop_sequence
    """)


def trips(con: duckdb.DuckDBPyConnection) -> None:
    """One row per scheduled trip: whether it was seen, when, and by what.

    Metro marks every trip SCHEDULED and never flags a cancellation, so a trip
    that did not run looks exactly like one that ran with its tracker off. This
    table records what was seen and leaves that judgement to later. It counts
    every report for the trip, including ones at stop sequences the timetable
    does not list, because a vehicle that reported at all was there.

    Run after match(), which builds the arrivals rows counted here.
    """
    con.execute("""
        CREATE OR REPLACE TABLE trips AS
        WITH seen AS (
            SELECT agency, trip_id,
                   count(*)                   AS reports,
                   min(ts)                    AS first_ts,
                   max(ts)                    AS last_ts,
                   count(DISTINCT vehicle_id) AS vehicles,
                   -- The vehicle that reported first, ties broken by id so a
                   -- rerun agrees. _null keeps an id-less first report as
                   -- unknown instead of naming a later vehicle.
                   arg_min_null(vehicle_id, {'t': ts, 'v': vehicle_id}) AS first_vehicle
            FROM observations
            GROUP BY agency, trip_id
        ),
        planned AS (
            SELECT service_date, agency, line, route_id, direction_id, trip_id,
                   min(scheduled_time)                       AS scheduled_start,
                   max(scheduled_time)                       AS scheduled_end,
                   count(*)                                  AS stops_scheduled,
                   count(*) FILTER (WHERE source <> 'none')  AS stops_observed
            FROM arrivals
            GROUP BY service_date, agency, line, route_id, direction_id, trip_id
        )
        SELECT p.*,
               coalesce(s.reports, 0)        AS reports,
               to_timestamp(s.first_ts)      AS first_seen,
               to_timestamp(s.last_ts)       AS last_seen,
               coalesce(s.vehicles, 0)       AS vehicles,
               s.first_vehicle               AS vehicle_id
        FROM planned p
        LEFT JOIN seen s USING (agency, trip_id)
    """)


# The layout version of everything written below. Bumped when a column is added
# or changes meaning, so a reader never mixes days written by different code.
# v1 lives at arrivals/service_date=... and is left where it is; v2 adds
# vehicle_id and departure_time to arrivals, and the trips table.
VERSION = "v2"

# What each table writes, and the order its rows go in. Sorted so a rerun over
# the same input writes the same rows in the same order.
TABLES = {
    "arrivals": """
        SELECT service_date, agency, line, route_id, direction_id, trip_id,
               stop_id, stop_sequence, scheduled_time, actual_time,
               delay_seconds, source, vehicle_id, departure_time,
               in_transit_seen, is_origin, is_terminus
        FROM arrivals ORDER BY agency, line, trip_id, stop_sequence
    """,
    "trips": """
        SELECT service_date, agency, line, route_id, direction_id, trip_id,
               scheduled_start, scheduled_end, stops_scheduled, stops_observed,
               reports, first_seen, last_seen, vehicles, vehicle_id
        FROM trips ORDER BY agency, line, trip_id
    """,
}


def partition(table: str, service_date: str) -> str:
    """Where one table's day lives, relative to the output root or the bucket.

    The trailing slash keeps a bucket prefix from matching any longer name
    that happens to start the same way, such as a stray `...-18-old/`.
    """
    stamp = f"{service_date[:4]}-{service_date[4:6]}-{service_date[6:]}"
    return f"{table}/{VERSION}/service_date={stamp}/"


def write(con: duckdb.DuckDBPyConnection, out: Path, service_date: str) -> dict[str, Path]:
    """Write the day's arrivals and trips, replacing whatever was there before.

    One date in, one partition per table out, and a rerun replaces only that
    partition. That property is what makes it safe to schedule this before it
    is perfect: any day can be recomputed later without touching any other day.
    """
    written = {}
    for table, query in TABLES.items():
        target = out / partition(table, service_date)
        if target.exists():
            for stale in target.glob("*.parquet"):
                stale.unlink()
        target.mkdir(parents=True, exist_ok=True)

        path = target / "part-0.parquet"
        con.execute(f"COPY ({query}) TO ? (FORMAT parquet, COMPRESSION zstd)", [str(path)])
        written[table] = path
    return written


def upload(client: storage.Client, written: dict[str, Path], service_date: str) -> list[str]:
    """Put one day's partitions in the derived bucket, replacing that day only.

    Anything already under the date's prefix is deleted first. Without that, a
    rerun that produced a different number of files would leave the old extras
    behind and every later read would silently double-count the overlap.

    Tables go up in the order given, and the report last. Before anything is
    deleted, the day's old report is removed, so with one writer per day a
    report in the bucket always sits beside complete tables: a regrade that
    dies partway leaves no report, and the next run grades the day again. Two
    processes grading the same day at once could still interleave, so the
    daily job and a backfill must not cover the same day at the same time.
    """
    bucket = client.bucket(DERIVED_BUCKET)
    if "reports" in written:
        for old in client.list_blobs(DERIVED_BUCKET, prefix=partition("reports", service_date)):
            old.delete()
    uploaded = []
    for table, path in written.items():
        prefix = partition(table, service_date)
        for stale in client.list_blobs(DERIVED_BUCKET, prefix=prefix):
            stale.delete()

        blob = bucket.blob(prefix + path.name)
        kind = "application/json" if path.suffix == ".json" else "application/vnd.apache.parquet"
        blob.upload_from_filename(path, content_type=kind)
        uploaded.append(f"gs://{DERIVED_BUCKET}/{blob.name}")
    return uploaded
