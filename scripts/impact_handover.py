"""Hand over a decided impact to the change story (Agent 0, C2).

Phase C runs without Agent 0: a person chooses the affected test cases and
this command does what the approval implies - Impacts links, the trace on
each owning story, the retired label, and ai-ready on the change story.
Agent 0 later calls the same core.impact_handover.handover() itself.

Decisions come from the command line, or from the change story's Impact
Review sub-task once it is Done:

    python -m scripts.impact_handover --story SCRUM-210 --approve SCRUM-3,SCRUM-4 --retire SCRUM-6
    python -m scripts.impact_handover --story SCRUM-210 --from-review
    python -m scripts.impact_handover --story SCRUM-210 --approve SCRUM-3 --dry-run

exit codes: 0 handed over (or dry run)   2 refused, nothing written
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


def _keys(value: str | None) -> list:
    return [k.strip().upper() for k in (value or "").split(",") if k.strip()]


def main(argv=None) -> int:
    from dotenv import load_dotenv
    load_dotenv()
    from core.impact_handover import HandoverRefused, decisions_from_review, handover
    from integrations.tracker import get_tracker

    ap = argparse.ArgumentParser(prog="python -m scripts.impact_handover",
                                 description="Hand a decided impact over to the change story.")
    ap.add_argument("--story", required=True, help="the change story, e.g. SCRUM-210")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--approve", help="comma-separated test case keys to revise")
    src.add_argument("--from-review", action="store_true",
                     help="read the decisions from the story's Impact Review (must be Done)")
    ap.add_argument("--retire", help="comma-separated test case keys to retire")
    ap.add_argument("--reject", help="comma-separated test case keys to leave alone")
    ap.add_argument("--dry-run", action="store_true", help="show what would happen; write nothing")
    args = ap.parse_args(argv)

    tracker = get_tracker()
    story = args.story.upper()
    review_key = None
    try:
        if args.from_review:
            review_key, decisions = decisions_from_review(tracker, story)
        else:
            decisions = {}
            for decision, keys in (("approve", args.approve), ("retire", args.retire),
                                   ("reject", args.reject)):
                for key in _keys(keys):
                    if key in decisions:
                        raise HandoverRefused(f"{key} is given two decisions")
                    decisions[key] = decision
        result = handover(tracker, story, decisions, review_key=review_key,
                          dry_run=args.dry_run)
    except HandoverRefused as e:
        print(f"REFUSED: {e}. Nothing was written.", file=sys.stderr)
        return 2

    print(f"{'DRY RUN - ' if result.dry_run else ''}Hand-over for {story}"
          + (f" (review {review_key})" if review_key else ""))
    print(f"  revise : {', '.join(result.approved) or '-'}")
    print(f"  retire : {', '.join(result.retired) or '-'}")
    print(f"  reject : {', '.join(result.rejected) or '-'}")
    for owner, keys in sorted(result.owners.items()):
        print(f"  owner {owner}: {', '.join(keys)}")
    if result.unowned:
        print(f"  WARNING no owning story: {', '.join(result.unowned)}")
    if not result.dry_run:
        print(f"  {story} is now ai-ready; trace posted on {len(result.comments_posted)} owner(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
