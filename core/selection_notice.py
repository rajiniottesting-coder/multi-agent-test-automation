"""One comment on a story that carries an agent's trigger label but that the
agent's scan will never take - its status or sprint is outside the selection.

The scan's query leaves such a story out, so nothing said why: on 4 Nov 2026
stories created outside the active sprint were analysed and released to
Agent 1, and then waited for a draft that never came. A trigger label on a
story whose status is outside the update selection (a Done story labelled for
an update) did the same.

Each story is told once per agent and reason: the comment carries a marker,
and a story whose comments already hold it for that reason is skipped. Needs
the tracker's optional `find_unselected_stories`; without it nothing happens.
Never raises - a notice must not stop a scan.
"""
from __future__ import annotations

import logging

from integrations.tracker import add_markdown_comment, capability

logger = logging.getLogger(__name__)

MARKER = "[pipeline:not-selected]"


def notice_text(agent: str, labels, why: str) -> str:
    labels = " ".join(f"`{x}`" for x in labels or []) or "its trigger label"
    return (f"{MARKER} {agent}: this story has {labels}, but the scan does not take it - "
            f"{why}. Nothing runs until that changes; the next scan after it does takes "
            "the story.")


def notify_unselected(tracker, selection: dict, agent: str, sprint_override=None,
                      dry_run: bool = False) -> list:
    """Post the notice on each labelled story the selection leaves out.
    Returns [(key, why)] for every such story (posted or already told)."""
    find = capability(tracker, "find_unselected_stories")
    if find is None or not selection:
        return []
    try:
        stories = find(selection, sprint_override=sprint_override) or []
    except Exception as e:                                         # noqa: BLE001
        logger.warning(f"{agent}: could not look for labelled stories outside the "
                       f"selection ({e}).")
        return []
    labels = selection.get("required_labels") or []
    seen = []
    for story in stories:
        key, why = story["key"], story["why"]
        seen.append((key, why))
        logger.warning(f"{agent}: {key} has {labels} but is not taken: {why}.")
        if dry_run:
            continue
        body = notice_text(agent, labels, why)
        try:
            if any(MARKER in str(c) and why in str(c) and agent in str(c)
                   for c in tracker.get_comments(key) or []):
                continue
            add_markdown_comment(tracker, key, body)
        except Exception as e:                                     # noqa: BLE001
            logger.warning(f"{agent}: could not tell {key} why it is not taken ({e}).")
    return seen
