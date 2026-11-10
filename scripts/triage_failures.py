"""Triage a run on main: defects, outages and flakes (F-22).

    python -m scripts.triage_failures --reports-dir reports --run-url <url> [--dry-run]

Runs in agent4_runner.yml after a run on `main` (the scheduled run, a push that
ran the E2E, a manual run on main), on the junit.xml Agent 4 finalised:

  failures  one open defect per test (core/defects.py)
  outages   one pipeline health alert while main runs hit the application's
            unavailability, with what the application health check found
            (reports/app_probe.json) when it found the application not up;
            it closes on the next run without one
  not run   one health alert for failures that were not run again: only a
  again     test that failed twice raises a defect (defects.only_after_retry)
  unmapped  one health alert for defects nothing traces to a test case or a
            story (labelled defects.unmapped_label)
  flakes    recorded on the pipeline health issue (core/flaky_tests.py)
  no report one health alert: the run on main produced nothing to read
  refused   one health alert when the tracker refused a defect write

Exit code 0 when everything found was recorded - the findings live on the
tracker, not in this job's colour. 1 when the tracker cannot be used or
refused a write: then the job's red run is the notice that still reaches
someone (the workflow's owner), even if the alert could not be posted.
"""
from __future__ import annotations

import argparse
import logging
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

logger = logging.getLogger("triage_failures")

NO_REPORT = "main-run-no-report"
NOT_WRITTEN = "defects-not-written"
OUTAGE = "application-unavailable-on-main"
CAPPED = "defects-capped"
NOT_RETRIED = "failures-not-retried"
UNMAPPED = "defects-unmapped"


def _probe_finding(junit: Path) -> str:
    """What the application health check found, when it found the application
    not up - the evidence for the outage alert."""
    try:
        import json
        probe = json.loads((junit.parent / "app_probe.json").read_text(encoding="utf-8"))
    except Exception:                                              # noqa: BLE001
        return ""
    if not isinstance(probe, dict) or probe.get("available") is not False:
        return ""
    return "\n\nThe application health check found: " + str(
        probe.get("summary") or probe.get("problem") or "the application not up")[:800]


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
              + _probe_finding(junit)
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
    if result.get("not_retried"):
        alert(tracker, NOT_RETRIED, f"{len(result['not_retried'])} failing test(s) on main "
                                    "were not run again - no defect raised",
              f"Run: {run_url}\n\n" + "\n".join(f"- `{t}`" for t in result["not_retried"][:25])
              + "\n\nA defect is raised only for a test that fails, is run again and fails "
                "again. These were not run again - usually more failures than the retry takes "
                "(MAX_RETRIED_TESTS in agent4_runner.yml), or a retry that did not run. Look "
                "at the run, then re-run the workflow. This alert closes on the next run on "
                "main where every failure was run again.")
    else:
        resolve(tracker, NOT_RETRIED, f"Every failing test on main was run again: {run_url}")
    untraced = list(result.get("unmapped") or [])
    stale = list(result.get("stale_trace") or [])
    if untraced or stale:
        alert(tracker, UNMAPPED, f"{len(untraced) + len(stale)} defect trace(s) on main need "
                                 "a person",
              f"Run: {run_url}\n\n"
              + ("Not traced to a test case or a story:\n"
                 + "\n".join(f"- {k}" for k in untraced[:25]) + "\n\n" if untraced else "")
              + ("Traced to an issue that no longer exists (a deleted or moved test case "
                 "or story - fix the scenario's marker or `defects.trace_owners`):\n"
                 + "\n".join(f"- {k}" for k in stale[:25]) + "\n\n" if stale else "")
              + "For an untraced one, nothing traces its test: no `# JIRA:` marker on the scenario, no "
                "story shared by the marked scenarios of its feature file, and no "
                "`defects.trace_owners` entry for the file. Add a marker (scripts/"
                "backfill_markers.py), or map the file in config.yaml. The next update "
                "links the defect and removes its unmapped label; this alert closes on the "
                "next run on main with no untraced defect.")
    else:
        resolve(tracker, UNMAPPED, f"Every defect on main is traced again: {run_url}")
    if result["errors"]:
        alert(tracker, NOT_WRITTEN, f"The tracker refused {len(result['errors'])} defect "
                                    "write(s) after a run on main",
              f"Run: {run_url}\n\n" + "\n".join(f"- {what}: {why[:300]}"
                                                for what, why in result["errors"][:10])
              + "\n\nUsually a field the defect's create screen requires, a link type "
                "`tracker.link_types` names that the tracker does not have, or a missing "
                "permission: check `defects.issue_type`, the link types and the bot account.")
    else:
        resolve(tracker, NOT_WRITTEN, f"Every defect write succeeded again: {run_url}")
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
    if out.get("errors"):
        print(f"[FAIL] the tracker refused {len(out['errors'])} write(s) - see above.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
