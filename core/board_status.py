"""Board column automation — keep the card where the work actually is.

WHY THIS EXISTS
---------------
Labels drive the agents; statuses tell a human at a glance what is happening.
Without this every story sits in "To Do" no matter how far it has progressed,
so the board is useless for standup.

This maps a completion LABEL onto a board STATUS:

    ai-processed  ->  In Progress     Agent 1 drafted test cases
    ai-coded      ->  In Review       Agent 2 opened a PR

and a MERGE onto the final column:

    PR merged     ->  Done            a human approved and merged the PR

Stories awaiting work (ai-ready / ai-update / ai-regenerate) keep whatever
status they have, which is normally "To Do".

Done is deliberately NOT driven by a label. No agent sets it, because no agent
merges: the merge is the human decision the whole pipeline is built around, so
the only thing that can move a card to Done is a real merge event.

TOOL-AGNOSTIC BY CONSTRUCTION
-----------------------------
The mapping lives in config.yaml, not in code, because column names differ per
tool and per team: Jira ships "To Do / In Progress / In Review / Done", Azure
DevOps uses "New / Active / Resolved / Closed", and plenty of boards are
customised beyond both. Moving a card goes through `Tracker.transition_status`,
so an adapter for a tracker with no workflow simply returns False.

NEVER FATAL
-----------
A failed move is logged and ignored. The pipeline has already done real work by
the time it moves a card; a workflow that forbids the transition, a renamed
column, or a permissions gap must not turn that into a failed run.
"""
from __future__ import annotations

import logging
from typing import Optional

import yaml

from config.paths import CONFIG_YAML

logger = logging.getLogger(__name__)


def load_status_workflow() -> dict:
    """Read the `status_workflow` block from config.yaml.

    Returns {"enabled": bool, "on_label": {label: status}}. A missing block
    means disabled, so an existing deployment behaves exactly as before.
    """
    try:
        data = yaml.safe_load(CONFIG_YAML.read_text(encoding="utf-8")) or {}
    except Exception as e:                       # unreadable config -> disabled
        logger.debug(f"status_workflow unreadable ({e}); board moves disabled.")
        return {"enabled": False, "on_label": {}}
    block = data.get("status_workflow") or {}
    if not isinstance(block, dict):              # `status_workflow: yes` etc.
        logger.warning("status_workflow is not a mapping; board moves disabled.")
        return {"enabled": False, "on_label": {}, "on_merge": None}
    return {"enabled": bool(block.get("enabled", False)),
            "on_label": _coerce_mapping(block.get("on_label"), "on_label"),
            "on_merge": _coerce_status(block.get("on_merge"), "on_merge"),
            "on_close_unmerged": _coerce_status(block.get("on_close_unmerged"),
                                                "on_close_unmerged")}


def _coerce_mapping(value, field: str) -> dict:
    """Return `value` as a {str: str} mapping, dropping anything unusable.

    YAML indentation mistakes turn a mapping into a string or a list, and a
    stray value turns a status into a dict. None of that should crash an agent
    mid-run, so bad entries are logged and skipped rather than raised.
    """
    if value is None:
        return {}
    if not isinstance(value, dict):
        logger.warning(
            f"status_workflow.{field} should be a mapping of label -> status, "
            f"got {type(value).__name__}. Ignoring it; no cards will move."
        )
        return {}
    out = {}
    for k, v in value.items():
        status = _coerce_status(v, f"{field}.{k}")
        if status:
            out[str(k)] = status
    return out


def _coerce_status(value, field: str) -> Optional[str]:
    """A status must be a non-empty string. Anything else is dropped."""
    if value is None:
        return None
    if not isinstance(value, str):
        logger.warning(
            f"status_workflow.{field} should be a status name (a string), got "
            f"{type(value).__name__}. Ignoring it."
        )
        return None
    return value.strip() or None


def status_for_label(label: str, workflow: Optional[dict] = None) -> Optional[str]:
    """Board status a given completion label should move the card to, or None.

    Never raises. A malformed config must not break a pipeline run that has
    already created test cases or opened a PR - board position is cosmetic.
    """
    try:
        wf = workflow if workflow is not None else load_status_workflow()
        if not isinstance(wf, dict) or not wf.get("enabled"):
            return None
        mapping = wf.get("on_label")
        if not isinstance(mapping, dict):
            mapping = _coerce_mapping(mapping, "on_label")
        return _coerce_status(mapping.get(label), f"on_label.{label}")
    except Exception as e:
        logger.warning(f"status_workflow is unusable ({e}); not moving the card.")
        return None


def move_card_for_label(tracker, issue_key: str, label: str,
                        workflow: Optional[dict] = None) -> bool:
    """Move `issue_key` to the status configured for `label`. True if moved.

    Call this straight after adding a completion label, so the card follows the
    state marker. Silent no-op when the feature is disabled or the label has no
    mapping - that is the default, and it keeps board automation opt-in.
    """
    status = status_for_label(label, workflow)
    if not status:
        return False
    try:
        moved = tracker.transition_status(issue_key, status)
        if moved:
            logger.info(f"Board: {issue_key} moved to {status!r} (label {label!r})")
        else:
            logger.info(
                f"Board: {issue_key} not moved to {status!r} - the tracker "
                f"declined the transition. Label {label!r} is still set, so the "
                f"pipeline is unaffected."
            )
        return moved
    except Exception as e:                       # never fatal
        logger.warning(f"Board: could not move {issue_key} to {status!r}: {e}")
        return False


def move_card_on_merge(tracker, issue_key: str,
                       workflow: Optional[dict] = None) -> bool:
    """Move a story to the `on_merge` status after its PR is merged.

    Separate from `move_card_for_label` on purpose: a merge is not a pipeline
    label, it is a HUMAN action. Agents 1 and 2 move cards because they did
    work; this moves a card because a person approved that work. Nothing in
    the agents calls it - it is driven by a merge event.

    Same never-fatal contract as every other board move.
    """
    try:
        wf = workflow if workflow is not None else load_status_workflow()
        if not isinstance(wf, dict) or not wf.get("enabled"):
            return False
        status = _coerce_status(wf.get("on_merge"), "on_merge")
    except Exception as e:
        logger.warning(f"status_workflow is unusable ({e}); not moving the card.")
        return False
    if not status:
        return False
    try:
        moved = tracker.transition_status(issue_key, status)
        logger.info(
            f"Board: {issue_key} moved to {status!r} (PR merged)" if moved else
            f"Board: {issue_key} not moved to {status!r} - the tracker declined "
            f"the transition. The merge itself is unaffected."
        )
        return moved
    except Exception as e:
        logger.warning(f"Board: could not move {issue_key} to {status!r}: {e}")
        return False

def move_card_on_close_unmerged(tracker, issue_key: str,
                                workflow: Optional[dict] = None) -> bool:
    """Move a story whose pull request was closed WITHOUT merging (and reset by
    reconcile, F-16) to the `on_close_unmerged` status. Unset: no move. Same
    never-fatal contract as every other board move."""
    try:
        wf = workflow if workflow is not None else load_status_workflow()
        if not isinstance(wf, dict) or not wf.get("enabled"):
            return False
        status = _coerce_status(wf.get("on_close_unmerged"), "on_close_unmerged")
    except Exception as e:
        logger.warning(f"status_workflow is unusable ({e}); not moving the card.")
        return False
    if not status:
        return False
    try:
        moved = tracker.transition_status(issue_key, status)
        logger.info(f"Board: {issue_key} moved to {status!r} (PR closed unmerged)" if moved
                    else f"Board: {issue_key} not moved to {status!r} - the tracker "
                         f"declined the transition.")
        return moved
    except Exception as e:
        logger.warning(f"Board: could not move {issue_key} to {status!r}: {e}")
        return False
