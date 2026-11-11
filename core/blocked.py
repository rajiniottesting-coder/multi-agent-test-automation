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
    if len(text) <= _MAX_ERROR_CHARS:
        return text
    cut = text[:_MAX_ERROR_CHARS - 3]
    # Never end inside a code span: an unclosed backtick is shown literally,
    # and the text after it loses its formatting (11 Nov 2026, a blocked
    # comment cut in the middle of `LoginPage`).
    if cut.count("`") % 2:
        cut = cut[:cut.rindex("`")].rstrip()
    return cut + "..."


def _missing_elements(errors) -> list:
    try:
        from validators.method_resolution_validator import elements_missing_from_inventory
        return elements_missing_from_inventory(errors)
    except Exception:                                              # noqa: BLE001
        return []


def _missing_pages(errors) -> list:
    try:
        from validators.method_resolution_validator import pages_missing_from_inventory
        return pages_missing_from_inventory(errors)
    except Exception:                                              # noqa: BLE001
        return []


# The method-resolution validator's wording for a call to a method a RESERVED
# page object lacks (validators/method_resolution_validator.py).
_RESERVED_CALL = re.compile(r"calls `\w+\.(\w+)\(\)`, but `(\w+)` does not define `\w+`\. "
                            r"`([^`]+)` is a RESERVED file")


# The selector check's wording for a new page object that borrows another
# page object's inventory page (validators/method_resolution_validator.py).
# validators.action_steps: a step worded as a click whose definition clicks nothing.
_ACTION_STEP = "Action step error"
# The plan's Skipped reason for an element the inventory lacks
# (prompts/agent2_coder_plan.md, decision step 3b).
_NOT_IN_INVENTORY = "not in the app inventory"
# validators.step_fidelity: a step whose code acts on or checks another element.
_STEP_FIDELITY = "Step fidelity error"
_BORROWED_PAGE = re.compile(r"class (\w+) sets INVENTORY_PAGE = '[^']+', the page \w+ "
                            r"\([^)]+\) implements, and resolves none of its elements")


def reserved_capabilities(errors) -> list:
    """`Class.method (file)` for each method a reserved page object would need.
    No repair can add one: Agent 2 may not edit a reserved file."""
    found = []
    for err in errors or []:
        for method, cls, path in _RESERVED_CALL.findall(str(err)):
            item = f"`{cls}.{method}` ({path})"
            if item not in found:
                found.append(item)
    return found


def _reasons_digest(errors) -> str:
    """8 hex characters over the refusal's errors. A retry on the same inputs
    that is refused for another reason (after a framework fix, say) is a new
    comment; the same refusal again is not."""
    text = "\x1e".join(sorted(str(e) for e in errors or []))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


def blocked_comment(story_id: str, fp: str, errors) -> str:
    errors = list(dict.fromkeys(str(e) for e in errors or [] if str(e).strip()))
    lines = [f"{BLOCKED_MARKER} inputs: {fp} reasons: {_reasons_digest(errors)}",
             (f"Agent 2 could not code {story_id}: the final gate refused the generated "
              "code for the reasons below (a rule still broken after every repair "
              "attempt, or no approved test case automated), so no pull request was "
              "opened."),
             ""]
    lines += [f"- {_short(e)}" for e in errors[:_MAX_ERRORS]]
    if len(errors) > _MAX_ERRORS:
        lines.append(f"- ... and {len(errors) - _MAX_ERRORS} more (see the Agent 2 run log)")
    missing = _missing_pages(errors)
    if missing:
        lines += ["",
                  (f"The story needs page(s) the app inventory does not have: "
                   f"{', '.join(missing)}. No repair can add a page - the inventory is "
                   "curated by a person. Add each one, then run Agent 2 with this "
                   "story's key: `python -m scripts.plan_inventory page --page <page> "
                   "--url /<path> --component \"<Component>\" --element <key>=\"<selector>\"` "
                   "(a page already live is confirmed and crawled by the next nightly "
                   "inventory update, which proposes its other elements). The other "
                   "errors above follow from the missing page.")]
        return "\n".join(lines)
    elements = _missing_elements(errors)
    if elements:
        lines += ["",
                  (f"The story needs element(s) the app inventory does not have: "
                   f"{', '.join(elements)}. No repair can add one - the inventory is "
                   "curated by a person. Add each one, then run Agent 2 with this "
                   "story's key: `python -m scripts.plan_inventory element --page <page> "
                   "--key <key> --selector \"<selector>\"` (the next nightly inventory "
                   "update confirms it once it is live). The other errors above follow "
                   "from the missing element.")]
        return "\n".join(lines)
    # The plan left test cases out for elements the inventory lacks (its
    # Skipped reason says "..., not in the app inventory"): the remedy is to
    # add them, not to edit the test cases.
    if any(_NOT_IN_INVENTORY in str(e) for e in errors):
        lines += ["",
                  ("The test cases above were left out because they need element(s) - or a "
                   "page - the app inventory does not have (each reason names them). No "
                   "repair can add one - the inventory is curated by a person. Add each "
                   "(`python -m scripts.plan_inventory element --page <page> --key <key> "
                   "--selector \"<selector>\"`; a page: `python -m scripts.plan_inventory "
                   "page --page <page> --url /<path> --component \"<Component>\" "
                   "--element <key>=\"<selector>\"`), then run Agent 2 with this story's key; "
                   "or retire the test cases that need them.")]
        return "\n".join(lines)
    borrowed = sorted({m for e in errors for m in _BORROWED_PAGE.findall(e)})
    if borrowed:
        lines += ["",
                  (f"A new page object ({', '.join(borrowed)}) has no inventory page of "
                   "its own: it names a page another page object implements and uses none "
                   "of its elements - usually because the page the story is about is not in "
                   "the app inventory. No repair can add a page - the inventory is curated "
                   "by a person. Add it (`python -m scripts.plan_inventory page --page <page> "
                   "--url /<path> --component \"<Component>\" --element <key>=\"<selector>\"`), "
                   "then run Agent 2 with this story's key.")]
        return "\n".join(lines)
    # Before the stand-in advice: a stand-in for a method a reserved page
    # object lacks is fixed by adding that method, not an inventory element
    # (11 Nov 2026: the inventory already had the element).
    reserved = reserved_capabilities(errors)
    if reserved:
        lines += ["",
                  ("The generated steps need what a reserved page object does not offer: "
                   f"{', '.join(reserved)}. Agent 2 may not edit a reserved file, so no "
                   "repair can add it. A person adds the method (its element must be in "
                   "the app inventory), or rewords the test case to use what the page "
                   "already offers; then run Agent 2 with this story's key (an edit to a "
                   "test case lets the next scheduled scan try again by itself).")]
        return "\n".join(lines)
    stood_in = [e for e in errors if str(e).startswith(_ACTION_STEP)]
    if stood_in:
        lines += ["",
                  ("A step says the user clicks a control, and no page-object call clicks it: "
                   "the generated code produced what the control would do instead. That is "
                   "almost always a control the app inventory has no key for. A person adds it "
                   "(`python -m scripts.plan_inventory element --page <page> --key <key> "
                   "--selector \"<selector>\"`), then runs Agent 2 with this story's key; or "
                   "retires the test case that needs it, so the others are coded.")]
        return "\n".join(lines)
    other_element = [e for e in errors if str(e).startswith(_STEP_FIDELITY)]
    if other_element:
        lines += ["",
                  ("A step's code acts on or checks a different element than the step names: "
                   "the generated code stood in for an element it could not reach. That is "
                   "almost always an element the app inventory has no key for. A person adds it "
                   "(`python -m scripts.plan_inventory element --page <page> --key <key> "
                   "--selector \"<selector>\"`; a page it lives on, `plan_inventory page`), "
                   "then runs Agent 2 with this story's key; or retires the test case that "
                   "needs it, so the others are coded.")]
        return "\n".join(lines)
    lines += ["",
              ("A rule that survives every repair usually means a test case asks for "
               "something this application cannot show as written. Change that test "
               "case (or the story) - any edit to them lets the next scheduled scan try "
               "again. Until then the scheduled scan skips this story and spends nothing. "
               "To retry without an edit (for example after a framework fix), run "
               "Agent 2 with this story's key.")]
    return "\n".join(lines)


def post_blocked_once(tracker, story_id: str, fp: str, errors) -> bool:
    """Post the blocked comment unless one for this input AND these reasons is
    already there. 4 Nov 2026: a story run again by key after a framework
    fix, was refused for a new reason (a reserved page object lacked the
    method) and the person was never told - the comment from the first
    refusal, on the same inputs, still blamed the old one. The scheduled scan
    skips a blocked story on its inputs alone (blocked_on), so the same
    refusal is never posted twice by it.
    Best-effort: returns whether it was posted, never raises."""
    try:
        head = f"{BLOCKED_MARKER} inputs: {fp} reasons: {_reasons_digest(errors)}"
        if any((c or "").startswith(head) for c in tracker.get_comments(story_id)):
            return False
        from integrations.tracker import add_markdown_comment
        add_markdown_comment(tracker, story_id, blocked_comment(story_id, fp, errors))
        return True
    except Exception as e:                                     # noqa: BLE001
        logger.warning("Could not post the blocked note on %s: %s", story_id, e)
        return False
