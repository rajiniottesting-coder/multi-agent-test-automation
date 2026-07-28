"""Move a story to the Done column after its PR is MERGED.

WHY THIS IS SEPARATE FROM THE AGENTS
------------------------------------
Every other board move is made by an agent that just did work: Agent 1 drafted
test cases, Agent 2 opened a PR. Done is different — it means a human read the
code and accepted it. No agent can know that, and no agent should claim it, so
Done is driven by a real merge event rather than a pipeline label.

That also makes the board honest. A card in Done means "a person merged this",
not "the robot thinks it is finished".

MERGED vs CLOSED
----------------
A PR closed WITHOUT merging is a rejection: the work was not accepted, so the
story must NOT move to Done. The workflow that calls this checks
`github.event.pull_request.merged`, and this script rechecks it, because a
closed-unmerged PR silently marked Done would be worse than no automation.

FULL FLAG REFERENCE
-------------------
    python -m scripts.close_merged_story --help

Usage:
    python -m scripts.close_merged_story --branch auto/SCRUM-5-login --merged true
    python -m scripts.close_merged_story --story SCRUM-5 --merged true
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import extract_jira_key
from core.board_status import load_status_workflow, move_card_on_merge
from integrations.tracker import get_tracker

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="python -m scripts.close_merged_story",
        description="Move a story to the Done column after its PR is merged.",
        epilog=("examples:\n"
                "  from a branch name   --branch auto/SCRUM-5-login --merged true\n"
                "  from a story key     --story SCRUM-5 --merged true\n"
                "  rejected PR (no-op)  --branch auto/SCRUM-5-login --merged false\n"
                "\nexit codes: 0=done (or correctly skipped)  2=no story key found"),
        formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--branch",
                     help="Head branch of the PR; the story key is parsed out of it.")
    src.add_argument("--story", help="Story key directly, e.g. SCRUM-5.")
    ap.add_argument("--merged", default="false",
                    help="'true' only if the PR was actually MERGED. A PR closed "
                         "without merging is a rejection and must not move the card.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Report what would happen; change nothing.")
    args = ap.parse_args()

    merged = str(args.merged).strip().lower() in ("true", "1", "yes")
    if not merged:
        print("PR was closed WITHOUT merging — the work was not accepted. "
              "Leaving the story where it is.")
        return 0

    story_key = args.story or extract_jira_key(args.branch or "")
    if not story_key:
        print(f"No story key found in branch {args.branch!r}. "
              f"Expected something like auto/PROJ-123-slug.", file=sys.stderr)
        return 2

    wf = load_status_workflow()
    if not wf.get("enabled") or not wf.get("on_merge"):
        print("status_workflow.on_merge is not configured — nothing to do.")
        return 0

    if args.dry_run:
        print(f"DRY RUN — would move {story_key} to {wf['on_merge']!r}.")
        return 0

    moved = move_card_on_merge(get_tracker(), story_key)
    print(f"{story_key}: {'moved to ' + wf['on_merge'] if moved else 'not moved (see log)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())