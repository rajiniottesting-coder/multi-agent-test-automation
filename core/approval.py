"""Only an allowed person's approval starts the coding agent (Group B, R5).

WHY
    Agent 2 codes every story labelled with the approval label
    (`human-approved`). Anyone who can edit an issue's labels could add it,
    and code would be generated and a pull request opened for test cases no
    reviewer read.

WHAT
    `agents.agent2_coder.approver_groups` names the tracker groups whose
    members may approve, and `agents.agent2_coder.approvers` lists people -
    each an account id, a display name or an email, as the tracker records
    them. A person passes when either matches. Both empty (the default) keeps
    today's behaviour: anyone. Groups keep names of people out of the
    repository.

    Before a story is coded, the tracker's history says who added the
    approval label last. Allowed -> coded as before. Not allowed, or unknown
    (the history cannot be read, or no approval is in it) -> not coded: the
    label is removed and ONE comment says who added it and who may approve.
    A person on the list adding the label again starts it.

    A tracker without a readable history (`changelog`) cannot be checked:
    with a non-empty list the story is NOT coded, and the log says so - an
    allow-list that silently lets everyone through is no allow-list.

Generic: no application, person or project lives here; the list is config.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

MARKER = "[agent2:approval]"


def approvers(agent_config: dict) -> list[str]:
    return [str(a).strip() for a in (agent_config.get("approvers") or []) if str(a).strip()]


def approver_groups(agent_config: dict) -> list[str]:
    return [str(g).strip() for g in (agent_config.get("approver_groups") or []) if str(g).strip()]


def restricted(agent_config: dict) -> bool:
    return bool(approvers(agent_config) or approver_groups(agent_config))


def last_added_by(history: list[dict] | None, label: str) -> dict | None:
    """Who added `label` most recently, from a changelog (oldest first)."""
    for change in reversed(history or []):
        for item in change.get("items") or []:
            if item.get("field") != "labels":
                continue
            before = set((item.get("from") or "").split())
            after = set((item.get("to") or "").split())
            if label in after and label not in before:
                return {**(change.get("by") or {}), "at": change.get("at")}
    return None


def allowed(person: dict | None, allowed_list: list[str]) -> bool:
    if not person:
        return False
    names = {str(person.get(k) or "").strip().lower()
             for k in ("account_id", "name", "email")} - {""}
    return any(a.lower() in names for a in allowed_list)


def check(tracker, story_key: str, label: str, agent_config: dict) -> tuple[bool, str]:
    """(True, "") when the story may be coded; else (False, why)."""
    if not restricted(agent_config):
        return True, ""
    from integrations.tracker import capability
    read = capability(tracker, "changelog")
    if read is None:
        return False, ("the tracker's history cannot be read, so who approved is unknown "
                       "(an approver list is set)")
    person = last_added_by(read(story_key), label)
    if person is None:
        return False, f"no '{label}' label is in the story's history"
    if allowed(person, approvers(agent_config)):
        return True, ""
    groups = approver_groups(agent_config)
    member_of = capability(tracker, "user_groups")
    if groups and member_of is not None and person.get("account_id"):
        theirs = {g.lower() for g in member_of(person["account_id"]) or []}
        if any(g.lower() in theirs for g in groups):
            return True, ""
    who = person.get("name") or person.get("email") or person.get("account_id") or "someone"
    return False, f"'{label}' was added by {who}, who is not an allowed approver"


def refuse(tracker, story_key: str, label: str, why: str, dry_run: bool = False) -> None:
    """Remove the approval label and say why, once. Never raises."""
    logger.warning("%s not coded: %s", story_key, why)
    if dry_run:
        return
    try:
        tracker.remove_label(story_key, label)
    except Exception as e:                                         # noqa: BLE001
        logger.warning("%s: approval label not removed: %s", story_key, e)
    body = (f"{MARKER} Not coded: {why}. The `{label}` label was removed. "
            f"An allowed approver (`agents.agent2_coder.approver_groups` / `approvers`) "
            f"adds it again to start coding.")
    try:
        from integrations.tracker import add_markdown_comment
        add_markdown_comment(tracker, story_key, body)
    except Exception as e:                                         # noqa: BLE001
        logger.warning("%s: approval comment not posted: %s", story_key, e)


def gate(tracker, stories: list[dict], label: str, agent_config: dict,
         dry_run: bool = False) -> list[dict]:
    """The stories that may be coded; the others are refused (above)."""
    if not restricted(agent_config):
        return stories
    kept = []
    for story in stories:
        ok, why = check(tracker, story["key"], label, agent_config)
        if ok:
            kept.append(story)
        else:
            refuse(tracker, story["key"], label, why, dry_run)
    return kept
