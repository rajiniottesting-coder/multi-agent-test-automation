"""Settle every change story labelled impact-applied (Agent 0, C7).

Merged pull request -> trace line on each owner, impact-applied off.
Closed without merging on two consecutive scans -> revised test cases
restored from their snapshots (unless edited since), links and retired
labels removed, story labelled impact-reverted. See core/impact_reconcile.py.

    python -m scripts.impact_reconcile
    python -m scripts.impact_reconcile --story SCRUM-210

Runs whatever agents.agent0_impact.enabled and shadow_mode say: it acts only
on stories labelled impact-applied, which exist only after a hand-over - by a
person (scripts.impact_handover, phase C) or by Agent 0 (D5) - and a closed
pull request must be undone either way. Scheduled by the reconcile job in
.github/workflows/agent0_impact.yml, the one place it runs.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


def main(argv=None) -> int:
    from dotenv import load_dotenv
    load_dotenv()
    from core.impact_reconcile import reconcile_all, reconcile_story
    from core.impact_settings import impact_settings
    from integrations.repo_host import get_repo_host
    from integrations.tracker import get_tracker

    ap = argparse.ArgumentParser(prog="python -m scripts.impact_reconcile")
    ap.add_argument("--story", help="settle one change story only")
    args = ap.parse_args(argv)

    settings = impact_settings()
    tracker, host = get_tracker(), get_repo_host()
    results = ([reconcile_story(tracker, host, args.story.upper(), settings)] if args.story
               else reconcile_all(tracker, host, settings))
    for r in results:
        print(f"{r['story']}: {r['action']}" + (f" ({r.get('error')})" if r.get("error") else ""))
    return 1 if any(r["action"] == "error" for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
