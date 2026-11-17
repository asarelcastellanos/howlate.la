"""health.json: how the daily grading did lately, for the behind-the-scenes page.

It is built from the reports the pipeline saves beside each day's Parquet, so the
page shows the same checks the pipeline ran and nothing it did not.

**The file is public, so each field is picked by name.** A report also holds
agency lists, notes and whatever a later version adds. Copying the report
across would publish all of it, so a new report field stays out until it is
added here.

**Reports in the bucket come in two shapes.** Days graded by 0.3.0 and earlier
name the join check `join_rate` and have no explained_* stats. Days graded by
0.4.0 name it `matched_rate` and have them. A missing explained_* stat reads as
0, which is true, because the pipeline did not count the trips then.
"""

import json
import re
from pathlib import Path

from howlate_pipeline import __version__

# The page lists two weeks. The fetch downloads this many reports and no more.
RECENT_DAYS = 14

DAY = re.compile(r"\d{4}-\d{2}-\d{2}")


def parse(document: object) -> tuple[dict, list[dict]] | None:
    """One saved report as a day's row and its checks, or None when it cannot be used.

    The report comes from the bucket, so this is where its shape is checked.
    """
    try:
        stats = document["stats"]
        row = {
            "service_date": document["service_date"],
            "ok": document["ok"],
            "failed": [check["name"] for check in document["checks"] if not check["ok"]],
            "coverage_pct": round(stats["coverage"], 1),
            "explained_trips": stats.get("explained_trips", 0),
            "explained_pct": round(stats.get("explained_pct", 0), 1),
            "observations": stats["observations"],
        }
        checks = [check_row(check) for check in document["checks"]]
    except (KeyError, TypeError, AttributeError):
        return None
    if not (DAY.fullmatch(str(row["service_date"])) and isinstance(row["ok"], bool)):
        return None
    return row, checks


def check_row(check: dict) -> dict:
    """A check with the fields of its kind. A count's `expect` is called `expected` here."""
    row = {key: check[key] for key in ("name", "kind", "label", "ok", "value")}
    if check["kind"] == "count":
        return row | {"expected": check["expect"]}
    return row | {"low": check["low"], "high": check["high"]}


def document(reports: Path | None, last: str, days: int) -> dict:
    """The file's content, from the saved reports under `reports`.

    With no reports, as in a test or a local run that has none, `recent` and
    `checks` are empty and the rest comes from the run, so the file is always
    written and always valid.

    Reports for days after `last` are left out. The rest of the site stops at
    `last`, and this file must not name a day the other files lack.
    """
    found = []
    if reports is not None and reports.is_dir():
        for path in sorted(reports.glob("service_date=*/report.json")):
            try:
                parsed = parse(json.loads(path.read_text()))
            except (OSError, ValueError):
                parsed = None
            if parsed is None:
                print(f"  skipped the report in {path.parent.name}: unreadable or missing a field")
            elif parsed[0]["service_date"] <= last:
                found.append(parsed)
    found.sort(key=lambda pair: pair[0]["service_date"], reverse=True)
    found = found[:RECENT_DAYS]
    return {
        "pipeline_version": __version__,
        "last_day": last,
        "days": days,
        "recent": [row for row, _ in found],
        "checks": found[0][1] if found else [],
    }
