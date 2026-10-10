"""Reconcile: finish or undo every change story labelled impact-applied (C7).

After Agent 1's impact-aware run, Jira holds the REVISED text of each approved
test case while `main` still holds the old scenario. This scheduled scan
looks at each such story's pull requests and settles it:

  open                         nothing
  merged                       impact-applied off; a *merged* trace line on
                               each owning story
  closed without merging,      every revised test case whose text is still what
  seen on two consecutive      the change wrote (current hash == snapshot's new
  scans                        hash) gets its old text back; one edited since is
                               left for a person and named. Retired labels and
                               the Impacts links come off, a *restored* line
                               goes on each owner, and the story is labelled
                               impact-reverted.
  no PR after no_pr_days       one comment asking a person to decide

Why scheduled and not on the PR's closed event: the sweeper restarts a
stalled PR by closing and reopening it, which emits the same event. The
two-scan rule absorbs that - a close is acted on only when the SAME close
(same PR, same updated_at) is still in place on the next scan.

Stateless: the scan keeps its memory in marker comments on the change story
(`[agent0:reconcile] ...`), so it can run anywhere, any number of times.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, timezone

from core import impact_trace
from core.impact_settings import impact_settings

logger = logging.getLogger(__name__)

MARK = "[agent0:reconcile]"
_CLOSED = re.compile(r"^\[agent0:reconcile\] closed-unmerged pr: (\d+) updated: (\S+)", re.M)
_NO_PR = re.compile(r"^\[agent0:reconcile\] no-pr since: (\d{4}-\d{2}-\d{2})", re.M)


def _today(now) -> date:
    return (now or datetime.now(timezone.utc)).date()


def _owners(tracker, keys) -> dict:
    owners: dict = {}
    for key in keys:
        owner = tracker.get_parent_story_key(key)
        if owner:
            owners.setdefault(owner, []).append(key)
    return owners


def reconcile_story(tracker, host, story: str, settings: dict | None = None, now=None) -> dict:
    """Settle one change story; returns {"story", "action", ...}."""
    settings = settings or impact_settings()
    labels = settings["labels"]
    prs = host.find_prs_for_story(story)
    comments = tracker.get_comments(story)

    if any(p["state"] == "open" for p in prs):
        return {"story": story, "action": "open"}

    cases = tracker.get_impacted_test_cases(story, include_retired=True)
    keys = [c["key"] for c in cases]
    owners = _owners(tracker, keys)

    merged = next((p for p in prs if p.get("merged")), None)
    if merged:
        for owner, owned in sorted(owners.items()):
            if not impact_trace.already_posted(tracker.get_comments(owner), "merged",
                                               story, merged["url"]):
                tracker.add_comment(owner, impact_trace.merged(story, merged["url"], owned))
        tracker.remove_label(story, labels["applied"])
        return {"story": story, "action": "merged", "pr": merged["number"]}

    if prs:                                      # newest first: the latest close
        pr = prs[0]
        seen = {(int(n), u) for n, u in _CLOSED.findall("\n".join(comments))}
        if (pr["number"], pr["updated_at"]) not in seen:
            tracker.add_comment(story, f"{MARK} closed-unmerged pr: {pr['number']} "
                                       f"updated: {pr['updated_at']}\n"
                                       f"Pull request #{pr['number']} is closed without merging. "
                                       "If it is still closed on the next scan, the revised test "
                                       "cases are restored to their earlier text.")
            return {"story": story, "action": "pending-close", "pr": pr["number"]}
        return _revert(tracker, story, pr, cases, owners, labels)

    since = _NO_PR.findall("\n".join(comments))
    if not since:
        tracker.add_comment(story, f"{MARK} no-pr since: {_today(now).isoformat()}\n"
                                   "Labelled impact-applied, but no pull request exists yet.")
        return {"story": story, "action": "no-pr-noted"}
    age = (_today(now) - date.fromisoformat(since[0])).days
    if age >= settings["reconcile"]["no_pr_days"] and \
            f"{MARK} ask-a-person" not in "\n".join(comments):
        tracker.add_comment(story, f"{MARK} ask-a-person\nThe test cases were revised "
                                   f"{age} days ago and no pull request has been opened. "
                                   "Decide: run Agent 2 (add human-approved), or undo by "
                                   "closing the story's work and removing impact-applied.")
        return {"story": story, "action": "asked-a-person", "days": age}
    return {"story": story, "action": "waiting-for-pr", "days": age}


def _revert(tracker, story, pr, cases, owners, labels) -> dict:
    restored, left, unsnapped = [], [], []
    from agents.agent2_coder import compute_description_hash
    from integrations.tracker import tracker_settings
    retired_label = tracker_settings()["retired_label"]

    for case in cases:
        key = case["key"]
        if case.get("retired"):
            tracker.remove_label(key, retired_label)
        snap = impact_trace.latest_snapshot(tracker.get_comments(key), story)
        if snap is None:
            unsnapped.append(key)               # retired only, or never revised
        elif compute_description_hash(case.get("description", "")) == snap["new_hash"]:
            tracker.set_description(key, snap["old_description"], summary=snap["old_summary"])
            restored.append(key)
        else:
            left.append(key)                    # edited after the revision: a person decides
        tracker.unlink_issues(story, key, "impacts")

    for owner, owned in sorted(owners.items()):
        tracker.unlink_issues(story, owner, "impacts")
        mine = [k for k in owned if k in restored]
        if not impact_trace.already_posted(tracker.get_comments(owner), "restored",
                                           story, pr["url"]):
            tracker.add_comment(owner, impact_trace.restored(
                story, pr["url"], mine, [k for k in owned if k in left]))
    tracker.remove_label(story, labels["applied"])
    tracker.add_label(story, labels["reverted"])
    logger.info("Reverted %s: restored %s, left for a person %s", story, restored, left)
    return {"story": story, "action": "reverted", "pr": pr["number"],
            "restored": restored, "left_for_a_person": left, "no_snapshot": unsnapped}


def reconcile_all(tracker, host, settings: dict | None = None, now=None) -> list:
    settings = settings or impact_settings()
    stories = tracker.find_stories_to_process(
        {"issue_type": "Story", "required_labels": [settings["labels"]["applied"]]},
        max_results=100)
    out = []
    for s in stories:
        try:
            out.append(reconcile_story(tracker, host, s["key"], settings, now))
        except Exception as e:                                 # noqa: BLE001
            logger.error("Reconcile failed for %s: %s", s["key"], e, exc_info=True)
            out.append({"story": s["key"], "action": "error", "error": str(e)})
    return out
