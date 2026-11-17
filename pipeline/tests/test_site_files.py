"""A run publishes the files its build wrote, never what an earlier run left behind.

A reused disk (a laptop run, the backfill VM) keeps the files of the last build.
A line Metro dropped must not come back as a frozen file in the next run.
"""

import json

import test_write
from fixture_day import SERVICE_DATE, run_day

from howlate_pipeline import DERIVED_BUCKET, aggregate, arrivals, labels


def fixture(tmp_path):
    """The fixture day, loaded, with its rows kept in `base` so lines can be swapped."""
    con = run_day(tmp_path / "day")
    arrivals.write(con, tmp_path / "out", SERVICE_DATE)
    graded = arrivals.connect()
    span = aggregate.load(graded, tmp_path / "out" / "arrivals" / arrivals.VERSION)
    graded.execute("CREATE TABLE base AS SELECT * FROM a")
    catalogue = labels.load(graded, {"LACMTA": tmp_path / "day" / "gtfs_bus"})
    return graded, catalogue, span


def with_lines(con, lines):
    """Make the data hold the fixture's rows once under each of these line names."""
    copies = (f"SELECT * REPLACE ('{line}' AS line) FROM base" for line in lines)
    con.execute("CREATE OR REPLACE VIEW a AS " + " UNION ALL ".join(copies))


def test_a_line_dropped_between_runs_is_not_published_by_the_second(tmp_path):
    con, catalogue, (first, last, days) = fixture(tmp_path)
    out, client = tmp_path / "site", test_write.FakeClient([])

    with_lines(con, ["720", "754"])
    _, names = aggregate.build(con, catalogue, out, first, last, days)
    aggregate.upload(client, out, names, run="20261116T130000Z")
    assert "lines/754.json" in test_write.published(client)[1]

    with_lines(con, ["720"])
    _, names = aggregate.build(con, catalogue, out, first, last, days)
    count, _ = aggregate.upload(client, out, names, run="20261117T130000Z")

    run, files = test_write.published(client)
    pointer = json.loads(client.store[(DERIVED_BUCKET, aggregate.POINTER)])
    assert run == "20261117T130000Z"
    assert sorted(files) == sorted(names) == ["index.json", "lines/720.json", "status.json"]
    assert count == pointer["files"] == len(files)


def test_a_stray_file_in_the_output_directory_is_neither_uploaded_nor_deleted(tmp_path):
    con, catalogue, (first, last, days) = fixture(tmp_path)
    out, client = tmp_path / "site", test_write.FakeClient([])
    strays = ["notes.txt", "extra.json", "lines/old.json"]
    (out / "lines").mkdir(parents=True)
    for stray in strays:
        (out / stray).write_text("not ours")

    _, names = aggregate.build(con, catalogue, out, first, last, days)
    aggregate.upload(client, out, names, run="20261116T130000Z")

    _, files = test_write.published(client)
    assert sorted(files) == ["index.json", "lines/720.json", "status.json"]
    assert [(out / stray).read_text() for stray in strays] == ["not ours"] * len(strays)
