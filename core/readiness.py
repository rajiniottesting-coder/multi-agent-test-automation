"""Is a story ready to draft test cases from? (Group B, R1)

WHY
    Agent 1 drafted test cases for any story it was given. A story with no
    acceptance criteria gave the model nothing to hold a draft to: it
    invented what "done" means, a reviewer had to read every case against a
    story that never said, and the cost was paid for a draft that usually
    went back.

WHAT
    With `agents.agent1_analyst.readiness.require_acceptance_criteria` on, a
    story whose description has no "Acceptance criteria" list (the same
    parser the coverage check reads, core.acceptance_coverage) is not
    drafted: no model call, and the scan hands it back - the trigger label
    removed, ONE comment telling the product owner what to add. Adding the
    label again after the list is written drafts it.

    Off by default (a project turns it on), so a project whose stories carry
    their criteria another way keeps working.

Generic: the heading words and list shapes come from core.acceptance_coverage.
"""
from __future__ import annotations


def readiness_problem(story: dict, agent_config: dict) -> str:
    """'' when the story may be drafted; else why not, in one sentence."""
    rules = (agent_config or {}).get("readiness") or {}
    if not rules.get("require_acceptance_criteria"):
        return ""
    from core.acceptance_coverage import parse_acceptance_criteria
    if parse_acceptance_criteria(story.get("description")):
        return ""
    return "The story has no acceptance-criteria list, so a draft has nothing to be held to."
