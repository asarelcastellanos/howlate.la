"""The human-readable names for lines, directions and stops.

Kept out of the arrivals table on purpose. Names change when Metro rewrites a
timetable and the measurements do not, so binding them together would mean
rewriting a year of Parquet to fix a spelling.

Three of the obvious columns are unusable and this module exists mostly to work
around that:

    trip_headsign      empty on all 41,626 trips, in both feeds
    route_short_name   blank for every rail line
    destination_code   fully populated, zero blanks, and reads like a sign

So directions are named from destination_code in stop_times.txt. A direction can
carry more than one destination, the 720 runs to both Santa Monica and Westwood,
so the busiest one wins and becomes "toward Santa Monica (Rapid)".
"""

from pathlib import Path

import duckdb

from howlate_pipeline import RAIL_AGENCY


# Metro writes route descriptions in capitals. Title case reads better on a page
# but turns "DOWNTOWN LA" into "Downtown La", so the handful of tokens that are
# genuinely initialisms are put back.
KEEP = {"La": "LA", "Usc": "USC", "Ucla": "UCLA", "Lax": "LAX", "Cbd": "CBD",
        "Nb": "NB", "Sb": "SB", "Eb": "EB", "Wb": "WB", "Via": "via"}


def readable(text: str) -> str:
    """Title case that does not mangle the abbreviations Metro relies on."""
    return " ".join(KEEP.get(word, word) for word in text.strip().title().split())


def lines(con: duckdb.DuckDBPyConnection, directory: Path, agency: str) -> dict[str, dict]:
    """One label per line.

    Bus and rail name themselves in different columns. Bus fills route_short_name
    with the number riders use and route_desc with the corridor, "WESTWOOD -
    EXPOSITION PARK VIA SUNSET-ALVARADO". Rail leaves the number blank and puts
    "Metro A Line" in route_long_name.
    """
    rows = con.execute("""
        SELECT DISTINCT split_part(route_id, '-', 1) AS line,
               route_short_name, route_long_name, route_desc, route_type
        FROM read_csv(?, all_varchar = true)
    """, [str(directory / "routes.txt")]).fetchall()

    out = {}
    for line, short, long_name, desc, route_type in rows:
        rail = agency == RAIL_AGENCY
        out[line] = {
            "label": (long_name or line).strip() if rail else (short or line).strip(),
            "via": readable(desc or "") if not rail else "",
            "mode": "rail" if rail else "bus",
        }
    return out


def directions(con: duckdb.DuckDBPyConnection, directory: Path) -> dict[tuple[str, int], str]:
    """The place each direction is signed for, by how often it is signed for it."""
    # Counted first, ranked second. Ranking in the same query as the aggregate
    # would make the window refer to a column the GROUP BY has already collapsed.
    rows = con.execute("""
        SELECT line, direction_id, destination_code FROM (
            SELECT *, row_number() OVER (
                       PARTITION BY line, direction_id
                       ORDER BY stops DESC, destination_code
                   ) AS rank
            FROM (
                SELECT split_part(t.route_id, '-', 1) AS line,
                       CAST(t.direction_id AS INTEGER) AS direction_id,
                       st.destination_code, count(*) AS stops
                FROM read_csv(?, all_varchar = true) st
                JOIN read_csv(?, all_varchar = true) t USING (trip_id)
                WHERE st.destination_code IS NOT NULL AND st.destination_code <> ''
                GROUP BY 1, 2, 3
            )
        ) WHERE rank = 1
    """, [str(directory / "stop_times.txt"), str(directory / "trips.txt")]).fetchall()

    return {(line, direction): name.strip() for line, direction, name in rows}


def stops(con: duckdb.DuckDBPyConnection, directory: Path) -> dict[str, dict]:
    """Every stop's name and where it is.

    Coordinates arrive with leading spaces in the bus feed, so they are cast
    rather than trusted as text.
    """
    rows = con.execute("""
        SELECT stop_id, stop_name, TRY_CAST(stop_lat AS DOUBLE), TRY_CAST(stop_lon AS DOUBLE)
        FROM read_csv(?, all_varchar = true)
    """, [str(directory / "stops.txt")]).fetchall()

    return {
        stop_id: {"name": (name or stop_id).strip(), "lat": lat, "lon": lon}
        for stop_id, name, lat, lon in rows
        if lat is not None and lon is not None
    }


def load(con: duckdb.DuckDBPyConnection, directories: dict[str, Path]) -> dict:
    """Every label, from both feeds, keyed the way the arrivals table is keyed."""
    catalogue = {"lines": {}, "directions": {}, "stops": {}}

    for agency, directory in directories.items():
        for line, meta in lines(con, directory, agency).items():
            catalogue["lines"][(agency, line)] = meta
        for (line, direction), name in directions(con, directory).items():
            catalogue["directions"][(agency, line, direction)] = name
        for stop_id, meta in stops(con, directory).items():
            catalogue["stops"][(agency, stop_id)] = meta

    return catalogue
