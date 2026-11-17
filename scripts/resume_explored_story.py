#!/usr/bin/env python3
"""Start Agent 2 again on a story whose missing page was just added (PW1).

    python -m scripts.resume_explored_story --pr <number> [--dry-run]

Run by "Story Done on merge" for every merged pull request. One that is not an
exploration proposal (no `[inventory-explore]` line - core/page_explore.py) is
left alone. For one that is, Agent 2 is started on its story (the workflow
`handoff.workflows.agent2_coder` names, with `story_key`) - a run by key, so
the refusal that skipped the story on every scan does not skip it now. When
the story already has an open pull request, nothing is started: the story is
told to merge or close that one first. One comment on the story says which.

Exit code 0 whatever it found; 1 when the start was refused (a token without
`actions: write`, say) - the comment then says to start Agent 2 by hand.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import page_explore as pe

logger = logging.getLogger("resume_explored_story")


def resume(tracker_factory, host, pr_number: int, workflow: str, dry_run: bool = False) -> dict:
    """`tracker_factory` is called only for an exploration pull request: every
    other merge reads one pull request and nothing else."""
    body = (host.get_pr_metadata(pr_number) or {}).get("body") or ""
    parsed = pe.parse_body(body)
    if not parsed:
        return {"status": "not_an_exploration"}
    story, page = parsed
    from integrations.tracker import add_markdown_comment
    tracker = tracker_factory()

    def say(text: str) -> None:
        print(f"[{story}] {text}")
        if not dry_run:
            add_markdown_comment(tracker, story, f"{pe.MARKER} {text}")

    existing = host.find_open_pr_for_story(story)
    if existing:
        say(f"Page `{page}` is in the inventory now (pull request #{pr_number} merged). Agent "
            f"2 was not started: this story has an open pull request "
            f"(#{existing['number']}) - merge or close it, then run Agent 2 with this "
            "story's key.")
        return {"status": "story_pr_open", "story": story, "pr": existing["number"]}
    if not workflow:
        say(f"Page `{page}` is in the inventory now (pull request #{pr_number} merged). "
            "Run Agent 2 with this story's key (handoff.workflows.agent2_coder is not set).")
        return {"status": "no_workflow", "story": story}
    try:
        if not dry_run:
            host.dispatch_workflow(workflow, "main", {"story_key": story})
    except Exception as e:                                         # noqa: BLE001
        say(f"Page `{page}` is in the inventory now (pull request #{pr_number} merged), but "
            f"Agent 2 could not be started ({type(e).__name__}). Run Agent 2 with this "
            "story's key.")
        return {"status": "error", "story": story, "why": str(e)[:300]}
    say(f"Page `{page}` is in the inventory now (pull request #{pr_number} merged): Agent 2 "
        "is started on this story again.")
    return {"status": "started", "story": story}


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pr", type=int, required=True, help="the merged pull request")
    ap.add_argument("--dry-run", action="store_true", help="print; start and post nothing")
    args = ap.parse_args(argv)
    from core.ops_settings import section
    from integrations.repo_host import get_repo_host
    from integrations.tracker import get_tracker
    workflow = (section("handoff").get("workflows") or {}).get("agent2_coder", "")
    out = resume(get_tracker, get_repo_host(), args.pr, workflow, args.dry_run)
    print(f"resume: {out}")
    return 1 if out["status"] == "error" else 0


if __name__ == "__main__":
    sys.exit(main())
