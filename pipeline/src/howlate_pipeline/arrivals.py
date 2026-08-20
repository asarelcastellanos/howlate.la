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
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

import duckdb
from google.cloud import storage

from howlate_pipeline import DERIVED_BUCKET, RAW_BUCKET, ZONE, gtfs

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
    print(f"  raw: {len(wanted)} files across {len(partitions(service_date))} partitions, "
          f"{len(missing)} to download")

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
    con.execute(f"""
        CREATE OR REPLACE TABLE observations AS
        SELECT * FROM ({EXTRACT}) WHERE service_date = ?
          AND trip_id IS NOT NULL AND stop_sequence IS NOT NULL AND ts IS NOT NULL
    """, [files, service_date])


def load_schedule(con: duckdb.DuckDBPyConnection, directories: dict[str, Path],
                  service_date: str) -> None:
    """Every stop every running trip was scheduled to make, from both feeds."""
    base = gtfs.day_base(service_date)

    con.execute("CREATE OR REPLACE TABLE scheduled (agency VARCHAR, line VARCHAR, "
                "route_id VARCHAR, direction_id INTEGER, trip_id VARCHAR, stop_id VARCHAR, "
                "stop_sequence INTEGER, scheduled_arrival BIGINT, scheduled_departure BIGINT, "
                "is_origin BOOLEAN, is_terminus BOOLEAN)")

    for agency, directory in directories.items():
        services = sorted(gtfs.active_services(directory, service_date))
        con.execute("CREATE OR REPLACE TEMP TABLE active AS SELECT unnest(?) AS service_id",
                    [services])

        # GTFS times run past 24:00:00 for trips that cross midnight, so they are
        # read as an offset from the day's base instant and never as a clock.
        con.execute(f"""
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
        """, [str(directory / "stop_times.txt"), str(directory / "trips.txt"), agency])


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
        SELECT
          agency, trip_id, stop_sequence,
          min(ts) FILTER (WHERE status = 'STOPPED_AT')    AS first_stopped,
          max(ts) FILTER (WHERE status = 'STOPPED_AT')    AS last_stopped,
          max(ts) FILTER (WHERE status = 'IN_TRANSIT_TO') AS last_approach,
          count(*) FILTER (WHERE status = 'IN_TRANSIT_TO') > 0 AS in_transit_seen,
          count(DISTINCT stop_id) AS distinct_stop_ids,
          any_value(stop_id)      AS reported_stop_id
        FROM observations
        GROUP BY agency, trip_id, stop_sequence
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


def write(con: duckdb.DuckDBPyConnection, out: Path, service_date: str) -> Path:
    """Write the day, replacing whatever was there before.

    One date in, one partition out, and a rerun replaces only that partition.
    That property is what makes it safe to schedule this before it is perfect:
    any day can be recomputed later without touching any other day.
    """
    stamp = f"{service_date[:4]}-{service_date[4:6]}-{service_date[6:]}"
    target = out / "arrivals" / f"service_date={stamp}"
    if target.exists():
        for stale in target.glob("*.parquet"):
            stale.unlink()
    target.mkdir(parents=True, exist_ok=True)

    path = target / "part-0.parquet"
    con.execute("""
        COPY (
          SELECT service_date, agency, line, route_id, direction_id, trip_id,
                 stop_id, stop_sequence, scheduled_time, actual_time,
                 delay_seconds, source, in_transit_seen, is_origin, is_terminus
          FROM arrivals ORDER BY agency, line, trip_id, stop_sequence
        ) TO ? (FORMAT parquet, COMPRESSION zstd)
    """, [str(path)])
    return path


def upload(client: storage.Client, path: Path, service_date: str) -> str:
    """Put one day's partition in the derived bucket, replacing that day only.

    Anything already under the date's prefix is deleted first. Without that, a
    rerun that produced a different number of files would leave the old extras
    behind and every later read would silently double-count the overlap.
    """
    stamp = f"{service_date[:4]}-{service_date[4:6]}-{service_date[6:]}"
    prefix = f"arrivals/service_date={stamp}/"
    bucket = client.bucket(DERIVED_BUCKET)

    for stale in client.list_blobs(DERIVED_BUCKET, prefix=prefix):
        stale.delete()

    blob = bucket.blob(prefix + path.name)
    blob.upload_from_filename(path, content_type="application/vnd.apache.parquet")
    return f"gs://{DERIVED_BUCKET}/{blob.name}"
