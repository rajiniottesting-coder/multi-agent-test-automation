#!/usr/bin/env python3
"""Propose the inventory changes the nightly drift report implies, as one PR.

Run by the Agent 0 drift job right after `check_inventory_staleness --compare`:

    python -m scripts.propose_inventory_update --drift-report reports/drift.json
    python -m scripts.propose_inventory_update --drift-report reports/drift.json --dry-run

What it changes and what it leaves for a person: core/inventory_update.py.
--dry-run prints the update and the pull request body and writes nothing; so
does Agent 0's shadow mode (agents.agent0_impact.shadow_mode), like the drift
maintenance story.

Settings: agents.agent0_impact.inventory_update in config.yaml
(enabled, branch, max_additions_per_page, hold_ratio, code_dirs).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import inventory_update as iu
from core.app_context import PROJECT_ROOT, AppContext
from core.impact_settings import impact_settings

logger = logging.getLogger("propose_inventory_update")


def plan(drift: dict, root: Path, cfg: dict, inventory_file: str):
    """(update, original text) for the inventory at root/inventory_file."""
    original = (root / inventory_file).read_text(encoding="utf-8")
    upd = iu.build_update(drift, json.loads(original),
                          iu.keys_named_in_code(root, cfg["code_dirs"]),
                          max_additions_per_page=int(cfg["max_additions_per_page"]),
                          hold_ratio=float(cfg["hold_ratio"]))
    return upd, original


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Open or refresh the nightly inventory-update PR.")
    ap.add_argument("--drift-report", required=True,
                    help="JSON written by check_inventory_staleness --compare --json")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the update and the PR body; write nothing")
    args = ap.parse_args(argv)

    agent0 = impact_settings()
    cfg = iu.settings(agent0.get("inventory_update"))
    if not cfg["enabled"]:
        print("inventory_update.enabled is false - nothing proposed.")
        return 0

    report = Path(args.drift_report)
    if not report.is_file():
        print(f"No drift report at {report} - nothing proposed.")
        return 0
    drift = json.loads(report.read_text(encoding="utf-8"))
    if not drift.get("pages_checked"):
        # A crawl that measured nothing (login failed, site down) must never
        # close or replace an open proposal, nor propose removals.
        print("The drift report measured no page - nothing proposed, nothing closed.")
        return 0

    ctx = AppContext.load()
    upd, original = plan(drift, PROJECT_ROOT, cfg, ctx.inventory_file)
    digest = iu.content_hash(iu.dump_like(original, upd.inventory))
    print(f"replaced {len(upd.replaced)}, added {len(upd.added)}, removed {len(upd.removed)}; "
          f"kept {len(upd.kept_missing)}, held pages {len(upd.held_pages)}, "
          f"over cap {len(upd.over_cap)}, refused {len(upd.refused)}")

    if args.dry_run or agent0.get("shadow_mode"):
        # Agent 0's shadow mode reports and writes nothing - the drift
        # maintenance story follows the same switch.
        why = "--dry-run" if args.dry_run else "Agent 0 shadow mode"
        print(f"\n{why}: nothing written. The pull request body would be:\n")
        print(iu.render_body(upd, ctx.inventory_file, digest, drift.get("checked_at", "")))
        return 0

    from integrations.repo_host import get_repo_host
    out = iu.open_or_refresh(get_repo_host(), upd, inventory_path=ctx.inventory_file,
                             original=original, branch=cfg["branch"],
                             checked_at=drift.get("checked_at", ""))
    print(f"inventory update: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
