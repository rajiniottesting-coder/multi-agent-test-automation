"""Raise defects from a pull request's run (D6): its new test found an
application bug.

    python -m scripts.raise_pr_defects --pr 123 [--dry-run]

A pull request's failures go to its story's report only (by design: most are
the new test's own fault). When a person reads a failure as a real bug in the
application, they label the pull request `defects.raise_label`
(`raise-defect`); the *Raise defects from a pull request* workflow then runs
this on Agent 4's latest finished run of the pull request's head commit:

  - each failure that failed again on the retry raises or updates ONE defect,
    exactly as on main (core/defects.py triage, source={"pr": n}): traced to
    its test case and story, priority, environment, a person's covering defect
    followed instead of a duplicate; the summary says "fails on pull request
    #n";
  - nothing is judged passing, followed or re-tested from it - main's runs do
    that once the test is merged;
  - one comment on the pull request lists what was raised, and the label comes
    off (adding it again after a new run raises again).

Exit 1 when the tracker refused a write or cannot be used.
"""
from __future__ import annotations

import argparse
import logging
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

logger = logging.getLogger("raise_pr_defects")

MARKER = "[defects:raised-from-pr]"


def _lines(result: dict) -> list[str]:
    out = []
    for name, title in (("raised", "Raised"), ("updated", "Updated (already open)"),
                        ("followed", "Followed on a person's defect"),
                        ("expected", "Expected - the story awaits its deployment"),
                        ("not_retried", "Not run again - no defect (re-run the tests)"),
                        ("capped", "Not raised - over defects.max_new_per_run")):
        if result.get(name):
            out.append(f"- **{title}:** " + ", ".join(f"`{x}`" if name in (
                "expected", "not_retried", "capped") else str(x) for x in result[name]))
    return out


def run(tracker, host, pr: int, features_dir: Path, dry_run: bool = False) -> dict:
    from agents.agent3_reviewer import (RUNNER_ARTIFACT_PREFIX, RUNNER_REPORT_FILE,
                                        _completed_runner_run)
    from core import defects
    label = defects.settings().get("raise_label") or "raise-defect"
    meta = host.get_pr_metadata(pr)
    found = _completed_runner_run(host, pr, meta["head_branch"], wait_seconds=0,
                                  poll_seconds=0)
    xml = None
    if found and found.get("id") is not None:
        xml = host.get_run_artifact_file(found["id"], RUNNER_ARTIFACT_PREFIX,
                                         RUNNER_REPORT_FILE)
    if not xml:
        body = (f"{MARKER} No finished Agent 4 run with a test report on this pull "
                f"request's latest commit yet - nothing raised. Add `{label}` again once "
                f"*Run Tests* has finished.")
        result = {"report": False}
    else:
        root = ET.fromstring(xml)
        result = defects.triage(tracker, root, found.get("url") or "", features_dir,
                                dry_run=dry_run, source={"pr": pr})
        result["report"] = True
        listed = _lines(result)
        if listed:
            body = (f"{MARKER} At the `{label}` label, the failures of Agent 4's run "
                    f"({found.get('url')}) were raised as application defects:\n\n"
                    + "\n".join(listed)
                    + "\n\nOnce the test is merged, the runs on main keep each defect up "
                      "to date and say when it passes again.")
        else:
            body = (f"{MARKER} At the `{label}` label: nothing in Agent 4's run "
                    f"({found.get('url')}) failed twice - no defect raised.")
        if result.get("errors"):
            body += "\n\nThe tracker refused: " + "; ".join(
                f"{what}: {why[:200]}" for what, why in result["errors"][:5])
    if dry_run:
        print(body)
        return result
    host.post_pr_comment(pr, body)
    remove = getattr(host, "remove_pr_label", None)
    if remove is not None:
        remove(pr, label)
    return result


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pr", type=int, required=True)
    ap.add_argument("--features-dir", default=None)
    ap.add_argument("--dry-run", action="store_true", help="print what would be done")
    args = ap.parse_args(argv)
    from config.paths import FEATURES_DIR
    try:
        from integrations.repo_host import get_repo_host
        from integrations.tracker import get_tracker
        tracker, host = get_tracker(), get_repo_host()
    except Exception as e:                                         # noqa: BLE001
        print(f"[FAIL] the tracker or the repository host could not be used: {e}")
        return 1
    out = run(tracker, host, args.pr,
              Path(args.features_dir) if args.features_dir else FEATURES_DIR, args.dry_run)
    for name, value in out.items():
        print(f"{name}: {value}")
    return 1 if out.get("errors") else 0


if __name__ == "__main__":
    sys.exit(main())
