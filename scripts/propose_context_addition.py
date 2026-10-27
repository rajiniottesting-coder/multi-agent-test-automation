#!/usr/bin/env python3
"""Propose the notes addition for a story whose pull request merged (F-8).

Run by the Story Done on merge workflow after the card moves to Done:

    python -m scripts.propose_context_addition --branch auto/ABC-5-feature
    python -m scripts.propose_context_addition --story ABC-5 --dry-run

The story's feature is live (its tests passed) and its pull request is merged,
so its facts - rules, limits, messages, flow, test data - belong in the app
notes the next story on that feature is drafted from. One model call proposes
them for the story's Component modules; lines the notes already state are
dropped; a reviewed pull request carries the rest (core/context_update.py).

Nothing happens for a branch without a story key (framework work), when Agent 0
or `context_update.additions` is off, or when the addition was already
proposed. Agent 0's shadow mode and --dry-run print the pull request body.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.app_context import PROJECT_ROOT
from core.impact_settings import impact_settings

logger = logging.getLogger("propose_context_addition")


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Propose the notes a merged story adds.")
    who = ap.add_mutually_exclusive_group(required=True)
    who.add_argument("--branch", help="the merged pull request's head branch")
    who.add_argument("--story", help="the story key")
    ap.add_argument("--dry-run", action="store_true", help="print the PR body; write nothing")
    args = ap.parse_args(argv)

    from config import extract_jira_key
    story_key = (args.story or extract_jira_key(args.branch or "") or "").upper()
    if not story_key:
        print(f"No story key in {args.branch!r} - not a story pull request; nothing to add.")
        return 0

    settings = impact_settings()
    cu_cfg = settings.get("context_update") or {}
    if not settings.get("enabled") or not cu_cfg.get("enabled") or not cu_cfg.get("additions"):
        print("Agent 0, its context update or its additions are off - nothing proposed.")
        return 0
    dry = args.dry_run or bool(settings.get("shadow_mode"))

    from core import context_update as cu
    from core.llm_client import LLMClient, get_usage_summary, reset_usage
    from integrations.repo_host import get_repo_host
    from integrations.tracker import get_tracker

    from core.spend_budget import BudgetExceeded
    reset_usage()
    try:
        out = cu.propose_addition_for_story(get_tracker(), get_repo_host(),
                                            LLMClient(temperature=0.0), story_key, settings,
                                            PROJECT_ROOT, dry_run=dry)
    except BudgetExceeded as stop:
        # F-24: the merge is done; only the notes proposal waits. Say how to
        # get it, and keep the cost already spent on the story's ledger.
        print(f"[BUDGET] {stop} The notes addition for {story_key} was not proposed; run "
              f"this script for {story_key} once the budget allows it.")
        out = {"addition": "budget"}
    if out.get("addition") == "dry-run":
        why = "--dry-run" if args.dry_run else "Agent 0 shadow mode"
        print(f"{why}: nothing written. Files: {out['files']}\n\n{out['body']}")
        return 0
    print(f"notes addition for {story_key}: {out}")
    usage = get_usage_summary()
    if usage.get("llm_calls"):
        try:
            from core.usage_ledger import IMPACT_ANALYST, post_usage_to_story
            post_usage_to_story(story_key, IMPACT_ANALYST, usage, jira=get_tracker())
        except Exception as e:                                     # noqa: BLE001
            logger.warning("usage for %s not posted: %s", story_key, e)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
