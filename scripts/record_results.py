"""Record recent full test runs of the default branch in the results store (RP1).

    python -m scripts.record_results --store store/ [--limit 30]

Reads Agent 4's recent runs on the default branch (core.results_store says
which kinds count), and for each one not yet in the store takes the final
junit.xml from its `pytest-report-` artifact and appends it. A run whose
artifact is gone (kept 3 days) or that ran no application tests is skipped
and said so. Idempotent: re-running records nothing twice.

Needs the repository host's credentials (GITHUB_TOKEN with actions: read,
GITHUB_REPO) and, to trace each test to its test case and story, the
tracker's; without the tracker a test is traced by its scenario marker only.
Exit 0 always - a report that cannot be built must not hide a test result.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger("record_results")

WORKFLOW = "agent4_runner.yml"
ARTIFACT = "pytest-report-"
# Runs whose junit.xml is the application suite on the default branch.
FULL_RUN_EVENTS = ("schedule", "workflow_dispatch", "push")


def _tracer(features_dir: Path):
    """trace(test_id) -> {"test_case", "owner"}; the tracker when reachable."""
    from core.defects import trace_of
    try:
        from integrations.tracker import get_tracker
        tracker = get_tracker()
    except Exception as e:                                         # noqa: BLE001
        logger.info("Tracker not reachable (%s); tracing by markers only.", e)
        tracker = None
    cache: dict = {}

    def trace(test_id: str) -> dict:
        if test_id not in cache:
            cache[test_id] = trace_of(test_id, features_dir, tracker)
        return cache[test_id]
    return trace


def record(store: Path, host, features_dir: Path, branch: str, limit: int) -> dict:
    """Append every recent full run not yet in `store`. Returns counts."""
    from core import results_store as rs
    done = rs.recorded_run_ids(store)
    counts = {"recorded": 0, "already": 0, "no_report": 0, "not_full": 0}
    runs = host.get_workflow_runs(WORKFLOW, branch, limit=limit)
    trace = None
    for run in reversed(runs):                       # oldest first
        if run.get("status") != "completed" or run.get("conclusion") in ("cancelled", "skipped"):
            continue
        if run.get("event") not in FULL_RUN_EVENTS:
            counts["not_full"] += 1
            continue
        if run["id"] in done:
            counts["already"] += 1
            continue
        junit = host.get_run_artifact_file(run["id"], ARTIFACT, "junit.xml")
        if not junit:
            # A push that changed no test input runs the unit suite only and
            # uploads nothing; an older run's artifact has expired.
            counts["no_report"] += 1
            continue
        trace = trace or _tracer(features_dir)
        meta = {**run, "started": run.get("created_at")}
        cases = rs.case_records(junit, meta, trace)
        if rs.append(store, meta, cases):
            counts["recorded"] += 1
            logger.info("Recorded run %s (%s, %d tests)", run["id"], run.get("event"), len(cases))
    return counts


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--store", required=True, type=Path)
    ap.add_argument("--features", default=Path("features"), type=Path)
    ap.add_argument("--branch", default="main")
    ap.add_argument("--limit", type=int, default=30)
    args = ap.parse_args(argv)
    counts = {"recorded": 0}
    try:
        from integrations.repo_host import get_repo_host
        args.store.mkdir(parents=True, exist_ok=True)
        counts = record(args.store, get_repo_host(), args.features, args.branch, args.limit)
        print(f"Results store: {counts['recorded']} run(s) recorded, "
              f"{counts['already']} already there, {counts['no_report']} without a "
              f"test report (unit-only or expired), {counts['not_full']} not full runs.")
    except Exception as e:                                         # noqa: BLE001
        print(f"::warning::Results not recorded: {e}")
    # The workflow publishes only when something new was recorded.
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"recorded={counts.get('recorded', 0)}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
