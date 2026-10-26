"""A story the code-generation gate refused: say so once, and stop paying for it.

When Agent 2's final gate refuses a story, the run fails and writes nothing.
The scheduled scan then picked the same story up again 30 minutes later, with
the same story text and the same test cases, and failed the same way - a full
set of model calls and repairs each time (about $2.50 in the run that exposed
this), every half hour, and not a word on the story about why.

A gate refusal on unchanged input is not something a retry fixes. What fixes
it is a person changing the input - usually a test case that asks for
something the application cannot show as written. So:

- on a gate refusal, ONE comment goes on the story: the rules still broken and
  what to do. Its first line carries a fingerprint of the input (the story text
  and the text of every test case the run coded or revised);
- the scheduled scan skips a story whose current fingerprint matches that
  comment - nothing is generated and nothing is spent;
- any edit to the story or to one of those test cases changes the fingerprint,
  so the next scan tries again by itself. A manual run (story_key) always runs,
  which is how a person retries after a framework fix.

Stateless, like the other markers: the memory is the comment on the story.
Generic: nothing here names an application or a rule.
"""
from __future__ import annotations

import hashlib
import logging
import re

logger = logging.getLogger(__name__)

BLOCKED_MARKER = "[agent2:blocked]"
_SIGNATURE = re.compile(r"^\[agent2:blocked\] inputs: ([0-9a-f]{16})\b", re.M)
_MAX_ERRORS = 6
_MAX_ERROR_CHARS = 400


def fingerprint(story: dict, test_cases, revisions=()) -> str:
    """16 hex characters over the story text and every test case's key, summary
    and description. Order-independent; a change to any of them changes it."""
    parts = [str((story or {}).get("description") or ""),
             str((story or {}).get("summary") or "")]
    for tc in sorted(list(test_cases or []) + list(revisions or []),
                     key=lambda t: str(t.get("key", ""))):
        parts.append("\x1f".join(str(tc.get(f) or "") for f in ("key", "summary", "description")))
    return hashlib.sha256("\x1e".join(parts).encode("utf-8")).hexdigest()[:16]


def blocked_on(comments, fp: str) -> bool:
    """Is there a blocked comment for exactly this input?"""
    return any(fp in _SIGNATURE.findall(c or "") for c in comments or [])


def _short(error: str) -> str:
    text = " ".join(str(error).split())
    return text if len(text) <= _MAX_ERROR_CHARS else text[:_MAX_ERROR_CHARS - 3] + "..."


def blocked_comment(story_id: str, fp: str, errors) -> str:
    errors = list(dict.fromkeys(str(e) for e in errors or [] if str(e).strip()))
    lines = [f"{BLOCKED_MARKER} inputs: {fp}",
             (f"Agent 2 could not code {story_id}: the generated code still broke the "
              "rules below after every repair attempt, so no pull request was opened."),
             ""]
    lines += [f"- {_short(e)}" for e in errors[:_MAX_ERRORS]]
    if len(errors) > _MAX_ERRORS:
        lines.append(f"- ... and {len(errors) - _MAX_ERRORS} more (see the Agent 2 run log)")
    lines += ["",
              ("A rule that survives every repair usually means a test case asks for "
               "something this application cannot show as written. Change that test "
               "case (or the story) - any edit to them lets the next scheduled scan try "
               "again. Until then the scheduled scan skips this story and spends nothing. "
               "To retry without an edit (for example after a framework fix), run "
               "Agent 2 with this story's key.")]
    return "\n".join(lines)


def post_blocked_once(tracker, story_id: str, fp: str, errors) -> bool:
    """Post the blocked comment unless one for this input is already there.
    Best-effort: returns whether it was posted, never raises."""
    try:
        if blocked_on(tracker.get_comments(story_id), fp):
            return False
        tracker.add_comment(story_id, blocked_comment(story_id, fp, errors))
        return True
    except Exception as e:                                     # noqa: BLE001
        logger.warning("Could not post the blocked note on %s: %s", story_id, e)
        return False
