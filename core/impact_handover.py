"""Hand-over: what happens when an Impact Review is decided (Agent 0, C2).

One place does all of it, in this order:

1. `Impacts` link: change story -> each approved or retired test case
2. `Impacts` link: change story -> each owning story (the trace link)
3. one *will revise* trace comment on each owning story
4. the retired label on each retired test case
5. labels on the change story: impact-check and impact-proposed off, ai-ready on

Rejected test cases are left alone. If every test is rejected the change story
still becomes ai-ready - for its own new test cases only.

Idempotent: every step checks before it writes (links are idempotent in the
adapter, comments are checked with `impact_trace.already_posted`, labels are
set-like), so an interrupted hand-over is simply run again.

Phase C drives it from `python -m scripts.impact_handover`; Agent 0 calls the
same `handover()` once its review is decided (D5).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from core import impact_review, impact_trace
from core.impact_settings import impact_settings

logger = logging.getLogger(__name__)


@dataclass
class HandoverResult:
    change_story: str
    approved: list = field(default_factory=list)
    retired: list = field(default_factory=list)
    rejected: list = field(default_factory=list)
    owners: dict = field(default_factory=dict)          # owner -> [test keys]
    unowned: list = field(default_factory=list)          # test keys with no owner
    comments_posted: list = field(default_factory=list)  # owners commented this run
    dry_run: bool = False


class HandoverRefused(Exception):
    """The decisions cannot be handed over as they stand; nothing was written."""


def handover(tracker, change_story: str, decisions: dict, review_key: str | None = None,
             dry_run: bool = False, settings: dict | None = None) -> HandoverResult:
    """decisions: {test case key: 'approve' | 'retire' | 'reject'}."""
    settings = settings or impact_settings()
    labels = settings["labels"]

    open_rows = impact_review.undecided(decisions)
    if open_rows:
        raise HandoverRefused(f"undecided rows: {', '.join(open_rows)}")
    if change_story in decisions:
        raise HandoverRefused(f"{change_story} cannot impact itself")

    result = HandoverResult(change_story=change_story, dry_run=dry_run)
    for key, decision in sorted(decisions.items()):
        {"approve": result.approved, "retire": result.retired,
         "reject": result.rejected}[decision].append(key)

    own = {tc["key"] for tc in tracker.get_linked_test_cases(change_story)}
    clash = sorted(own & set(result.approved + result.retired))
    if clash:
        raise HandoverRefused(f"{change_story} owns {', '.join(clash)}: a story revises "
                              "its own test cases through its own run, not a hand-over")

    for key in result.approved + result.retired:
        owner = tracker.get_parent_story_key(key)
        if owner:
            result.owners.setdefault(owner, []).append(key)
        else:
            result.unowned.append(key)

    if dry_run:
        return result

    for key in result.approved + result.retired:
        tracker.link_issues(change_story, key, "impacts")
    for key in result.retired:
        tracker.add_label(key, _retired_label())

    summary = tracker.get_story(change_story).get("summary", "")
    for owner, keys in sorted(result.owners.items()):
        if owner == change_story:
            # Unreachable today: a story that owns an impacted test case is
            # refused above. Kept so a future change to that check can never
            # make a story link to, or post a trace on, itself.
            continue
        tracker.link_issues(change_story, owner, "impacts")
        comments = tracker.get_comments(owner)
        if impact_trace.already_posted(comments, "will-revise", change_story, review_key):
            continue
        tracker.add_comment(owner, impact_trace.will_revise(
            change_story, summary,
            revised=[k for k in keys if k in result.approved],
            retired=[k for k in keys if k in result.retired],
            review=review_key))
        result.comments_posted.append(owner)

    # Label lifecycle (design section 9): the previous impact- label goes in
    # the same step that adds the next one.
    for label in (labels["check"], labels["proposed"]):
        tracker.remove_label(change_story, label)
    tracker.add_label(change_story, labels["ready"])
    logger.info("Hand-over for %s: approved %s, retired %s, rejected %s, owners %s",
                change_story, result.approved, result.retired, result.rejected,
                sorted(result.owners))
    return result


def decisions_from_review(tracker, change_story: str, settings: dict | None = None) -> tuple:
    """(review key, decisions) from the change story's latest Impact Review.

    Raises HandoverRefused while the review is missing or not yet Done.
    """
    settings = settings or impact_settings()
    prefix = settings["review"]["summary_prefix"]
    reviews = [s for s in tracker.get_subtasks(change_story)
               if s["summary"].startswith(prefix)]
    if not reviews:
        raise HandoverRefused(f"{change_story} has no {prefix} sub-task")
    review = reviews[-1]
    if review["status"].strip().lower() != settings["review"]["done_status"].strip().lower():
        raise HandoverRefused(f"{review['key']} is {review['status']!r}, not "
                              f"{settings['review']['done_status']!r}")
    return review["key"], impact_review.parse(review["description"])


def _retired_label() -> str:
    from integrations.tracker import tracker_settings
    return tracker_settings()["retired_label"]
