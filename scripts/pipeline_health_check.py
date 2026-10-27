"""The scheduled pipeline health check (F-23).

    python -m scripts.pipeline_health_check            # check, alert, refresh
    python -m scripts.pipeline_health_check --dry-run  # print findings only

Order:
  1. The tracker's credentials. Without them no alert can be posted, so this
     run fails red instead (GitHub then notifies the workflow's owner) - the
     one problem that cannot be reported on the health issue.
  2. Scheduled workflows failing `consecutive_failures` scheduled runs in a row.
  3. The repo host's token (refused, or close to expiry where the host says).
  4. The model endpoint (`pipeline_health.model_check`).
Each finding opens or closes its alert on the health issue; an alert that is
already in that state posts nothing. Then the issue's description is refreshed.

Exit code: 0 whenever the findings were recorded - an open alert is reported
on the issue, not by failing this run, or this workflow would itself become a
failing scheduled workflow and alert about itself. 1 when the tracker could
not be used.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import logging
import re
import sys
from pathlib import Path

logger = logging.getLogger("pipeline_health_check")

# This workflow is not watched by itself: when it fails, it cannot post.
OWN_WORKFLOW = "pipeline_health.yml"


def findings(tracker, host_factory, root: Path, now: _dt.datetime) -> list:
    from core import health_checks as hc
    from core.pipeline_health import settings
    s = settings()
    out = []
    try:
        host = host_factory()
        out += hc.workflow_findings(host, root, int(s["consecutive_failures"]),
                                    exclude=(OWN_WORKFLOW,))
    except Exception as e:                                         # noqa: BLE001
        logger.warning("Scheduled workflows not checked: %s", e)
    out += hc.repo_host_findings(host_factory, now, int(s["expiry_warn_days"]))
    model = hc.check_model(s.get("model_check", "completion"))
    if model:
        out.append(model)
    return out


def apply(tracker, found: list) -> dict:
    """Open or close each alert. Returns {"opened": [...], "resolved": [...]}."""
    from core import pipeline_health as ph
    opened, resolved = [], []
    for f in found:
        if f.problem:
            if ph.raise_alert(tracker, f.alert_id, f.title, f.detail):
                opened.append(f.alert_id)
        elif ph.resolve_alert(tracker, f.alert_id, f.title + "."):
            resolved.append(f.alert_id)
    return {"opened": opened, "resolved": resolved}


def housekeeping(tracker, now: _dt.datetime) -> None:
    """Old records go, so the issue's record list stays short. Never raises."""
    try:
        from core import flaky_tests, pipeline_health as ph, spend_budget
        flaky_tests.prune(tracker, now)
        keep = int(ph.settings().get("spend_keep_days", 35))
        ph.prune(tracker, spend_budget.SPEND_PREFIX,
                 (now - _dt.timedelta(days=keep)).strftime("%Y%m%d"))
        # A day's budget alerts end with the day (F-24).
        today = spend_budget.day_of(now)
        ph.resolve_where(tracker, lambda a: bool(re.fullmatch(r"budget-(day|warn)-\d{8}", a))
                         and a.rsplit("-", 1)[1] < today,
                         "A new day: the daily budget starts again.")
    except Exception as e:                                         # noqa: BLE001
        logger.warning("Housekeeping skipped: %s", e)


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true", help="print the findings; write nothing")
    ap.add_argument("--root", default=".", help="repository checkout (for the workflow files)")
    args = ap.parse_args(argv)

    from core import pipeline_health as ph
    from integrations.repo_host import get_repo_host
    from integrations.tracker import capability, get_tracker
    if not ph.settings().get("enabled"):
        print("pipeline_health.enabled is false - nothing to do.")
        return 0
    now = _dt.datetime.now(_dt.timezone.utc)
    try:
        tracker = get_tracker()
        check = capability(tracker, "check_access")
        who = (check() or {}).get("who") if check else "?"
        print(f"[OK] tracker credentials ({who})")
    except Exception as e:                                         # noqa: BLE001
        from core.health_checks import _redact
        print(f"[FAIL] the tracker refused the pipeline's credentials: "
              f"{type(e).__name__}: {_redact(str(e))[:300]}")
        print("No alert can be posted; this run fails so that the workflow's owner is told.")
        return 1

    found = findings(tracker, lambda: get_repo_host(), Path(args.root), now)
    for f in found:
        print(f"[{'ALERT' if f.problem else 'OK'}] {f.alert_id}: {f.title}")
    if args.dry_run:
        return 0
    if not ph.issue_key(tracker):
        print("[FAIL] no pipeline health issue could be found or created - see the log.")
        return 1
    result = apply(tracker, found)
    housekeeping(tracker, now)
    ph.refresh_view(tracker, now)
    print(f"opened: {result['opened'] or 'none'}; resolved: {result['resolved'] or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
