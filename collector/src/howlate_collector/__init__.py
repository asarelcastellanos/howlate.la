"""Records where LA Metro's buses and trains actually are.

Three processes, deployed separately and deliberately unable to break each
other. They share no state and never call each other:

    record.py     holds both websockets open, writes to disk    continuous
    upload.py     ships finished files to Cloud Storage         continuous
    timetable.py  saves the schedules when Metro changes them   every 6h

record and upload speak only through filenames in the spool directory, so if
Cloud Storage is unreachable the recorder neither knows nor cares. Collection
never depends on upload succeeding.

    routes.py     the lines subscribed to, shared by record and timetable
    spool.py      the file on disk and its lifecycle, used by record

Nothing here interprets the data. That is the pipeline's job, later, against an
archive that is already safe.
"""

__version__ = "0.1.0"

# Both upload.py and timetable.py write here. Kept in one place because two
# copies that drifted apart would split the archive in two without any error.
BUCKET = "howlate-raw"
