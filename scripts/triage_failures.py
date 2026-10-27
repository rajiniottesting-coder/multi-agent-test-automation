"""Triage a run on main: defects, outages and flakes (F-22).

    python -m scripts.triage_failures --reports-dir reports --run-url <url> [--dry-run]

Runs in agent4_runner.yml after a run on `main` (the scheduled run, a push that
ran the E2E, a manual run on main), on the junit.xml Agent 4 finalised:

  failures  one defect per test and cause (core/defects.py)
  outages   one pipeline health alert while main runs hit the application's
            unavailability; it closes on the next run without one
  flakes    recorded on the pipeline health issue (core/flaky_tests.py)
  no report one health alert: the run on main produced nothing to read

Exit code 0 unless the tracker cannot be used: the findings live on the
tracker, not in this job's colour.
"""
from __future__ import annotations

import argparse
import logging
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

logger = logging.getLogger("triage_failures")

NO_REPORT = "main-run-no-report"
OUTAGE = "application-unavailable-on-main"
CAPPED = "defects-capped"


def run(tracker, junit: Path, run_url: str, features_dir: Path, dry_run: bool = False) -> dict:
    from core import defects, flaky_tests, junit_marks as jm, pipeline_health as ph
    alert = (lambda *a, **k: None) if dry_run else ph.raise_alert
    resolve = (lambda *a, **k: None) if dry_run else ph.resolve_alert
    try:
        root = ET.parse(junit).getroot()
    except (OSError, ET.ParseError) as e:
        alert(tracker, NO_REPORT, "A run on main produced no readable test report",
              f"{type(e).__name__}: {e}. Run: {run_url}. The tests on main were not checked; "
              "open the run to see why.")
        return {"report": False}
    resolve(tracker, NO_REPORT, f"A run on main produced a report again: {run_url}")

    result = defects.triage(tracker, root, run_url, features_dir, dry_run=dry_run)
    if result["outages"]:
        n = len(result["outages"])
        alert(tracker, OUTAGE, f"{n} test(s) could not run on main: the application was "
                               "unavailable",
              f"Run: {run_url}\n\n" + "\n".join(f"- `{t}`" for t in result["outages"][:25])
              + "\n\nNo defect is raised for these. This alert closes on the next run on "
                "main without an outage.")
    else:
        resolve(tracker, OUTAGE, f"The next run on main had no outage: {run_url}")
    if result["capped"]:
        alert(tracker, CAPPED, f"{len(result['capped'])} more failing test(s) on main than "
                               "defects raised",
              f"Run: {run_url}. Raised {len(result['raised'])} (defects.max_new_per_run); not "
              "raised:\n" + "\n".join(f"- `{t}`" for t in result["capped"][:25])
              + "\n\nThat many new failures at once is usually a broken build or an "
                "environment problem - look at the run first.")
    else:
        resolve(tracker, CAPPED, f"Every failing test on main has a defect again: {run_url}")
    if result["flaky"] and not dry_run:
        cases = {jm.case_id(c): c for c in jm.cases(root)}
        flaky_tests.record(tracker, [(t, jm.props(cases[t]).get("first_failure"))
                                     for t in result["flaky"]], run_url)
    return {"report": True, **result}


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--reports-dir", default="reports")
    ap.add_argument("--run-url", default="")
    ap.add_argument("--features-dir", default=None)
    ap.add_argument("--dry-run", action="store_true", help="print what would be done")
    args = ap.parse_args(argv)
    from config.paths import FEATURES_DIR
    from integrations.tracker import get_tracker
    try:
        tracker = get_tracker()
    except Exception as e:                                         # noqa: BLE001
        print(f"[FAIL] the tracker could not be used: {type(e).__name__}: {e}")
        return 1
    out = run(tracker, Path(args.reports_dir) / "junit.xml", args.run_url,
              Path(args.features_dir) if args.features_dir else FEATURES_DIR, args.dry_run)
    for name, value in out.items():
        print(f"{name}: {value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
