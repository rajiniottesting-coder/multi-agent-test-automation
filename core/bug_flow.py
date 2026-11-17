"""A production bug gets a regression test (D3).

WHY
    Only stories started Agents 1 and 2. A bug a person raised from
    production - steps to reproduce, the result expected, the result seen -
    never became a test, so the same bug could come back unseen: the suite
    covered what stories asked for, not what had already broken.

WHAT
    With `bug_flow.enabled`, an issue of `bug_type` is worked like a story of
    `story_type`, through the same labels, scans and approvals:

    selection  every selection of the story type also takes bugs (the
               tracker adapter widens it - integrations/jira_client.py
               `_type_clause`), except the triage's own defects (`defects.
               label`): those already are a failing test;
    readiness  a bug without an expected result is not drafted - its
               regression test would have nothing to assert (no model call,
               handed back with one comment, as R1);
    criteria   without an acceptance-criteria list, its expected results are
               what the draft is held to: EXP1..EXPn, each mapped to the test
               case that asserts it (core/acceptance_coverage.py);
    drafting   Agent 1's prompt is told it is a bug report: follow the steps
               to reproduce and assert the EXPECTED result, never the actual
               one (prompts/agent1_bug_report.md) - so the test fails while
               the bug is there and passes once it is fixed;
    pending    an open bug is marked awaiting its deployment (X4,
               `deployment.pending_label`) when its test cases are drafted: its
               regression test fails until the fix is live, so the pull request
               reports that failure as expected and the run on main raises no
               second defect. `deployment.deployed_label` (or the deployment
               signal) ends it; from then on a failure is followed on the bug
               itself (D1: the bug owns the test case) and a pass says so;
    merge      merging the regression test does not close the bug
               (`done_on_merge` false): the test is in, the fix may not be.
               The bug gets one comment instead.

    The bug owns its test cases (`link_types.owns`), so the matrix, Agent 5's
    report, the impact graph and the defect triage find it as they find a
    story.

    Off by default: a project that does not turn it on is unchanged.

Generic: issue types, heading words and labels come from config.
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

MARKER = "[bug-flow]"
PROMPT_FILE = "agent1_bug_report.md"


def settings() -> dict:
    from core.ops_settings import section
    return section("bug_flow")


def enabled(s: dict | None = None) -> bool:
    return bool((s or settings()).get("enabled"))


def is_bug_type(issue_type, s: dict | None = None) -> bool:
    """`issue_type` is the bug type, and the bug flow is on."""
    s = s or settings()
    return enabled(s) and str(issue_type or "").strip().lower() == str(
        s.get("bug_type") or "").strip().lower()


def is_bug(issue: dict | None, s: dict | None = None) -> bool:
    return is_bug_type((issue or {}).get("issue_type"), s)


def owner_types(s: dict | None = None) -> list:
    """The issue types that own test cases: the story type, and the bug type
    when the bug flow is on."""
    s = s or settings()
    types = [s.get("story_type") or "Story"]
    if enabled(s) and s.get("bug_type"):
        types.append(s["bug_type"])
    return types


def widened(issue_type, s: dict | None = None):
    """A selection's issue type, with the bug type added when it asks for the
    story type and the bug flow is on: (types, label a bug must not carry).
    Anything else is returned as it was, with no label."""
    s = s or settings()
    if not enabled(s) or isinstance(issue_type, (list, tuple)) or \
            str(issue_type or "").strip().lower() != str(s.get("story_type") or "").lower():
        return issue_type, None
    from core.ops_settings import section
    return [s["story_type"], s["bug_type"]], (section("defects").get("label") or None)


# ── reading a bug report ──────────────────────────────────────────────

def _items(description, names, s: dict) -> list:
    from core.acceptance_coverage import heading_pattern, parse_section_items
    stops = [h for key in ("expected_headings", "actual_headings", "steps_headings")
             for h in s.get(key) or [] if h not in names]
    return parse_section_items(description, heading_pattern(names), heading_pattern(stops))


def expected_results(description, s: dict | None = None) -> list:
    """The items under the bug's expected-result heading, in order."""
    s = s or settings()
    return _items(description, s.get("expected_headings") or [], s)


def steps_to_reproduce(description, s: dict | None = None) -> list:
    s = s or settings()
    return _items(description, s.get("steps_headings") or [], s)


def actual_results(description, s: dict | None = None) -> list:
    s = s or settings()
    return _items(description, s.get("actual_headings") or [], s)


def readiness_problem(issue: dict, s: dict | None = None) -> str:
    """'' when the bug may be drafted; else why not, in one sentence."""
    s = s or settings()
    from core.acceptance_coverage import parse_acceptance_criteria
    description = issue.get("description")
    if parse_acceptance_criteria(description) or expected_results(description, s):
        return ""
    heads = ", ".join(f"'{h.title()}'" for h in (s.get("expected_headings") or [])[:2])
    return (f"The bug has no expected result (a {heads} section), so its regression test "
            "would have nothing to assert.")


def prompt_block(issue: dict, s: dict | None = None) -> str:
    """What Agent 1 is told about a bug report: the prompt fragment with the
    steps, the expected and the actual results read out of it."""
    s = s or settings()
    from config.paths import PROMPTS_DIR
    template = (Path(PROMPTS_DIR) / PROMPT_FILE).read_text(encoding="utf-8")

    def listed(items):
        return "\n".join(f"{n}. {t}" for n, t in enumerate(items, 1)) or "(not given)"
    description = issue.get("description")
    return (template
            .replace("{steps}", listed(steps_to_reproduce(description, s)))
            .replace("{expected}", listed(expected_results(description, s)))
            .replace("{actual}", listed(actual_results(description, s))))


# ── after drafting, and at merge ──────────────────────────────────────

def mark_pending(tracker, issue: dict, s: dict | None = None) -> bool:
    """An open bug waits for its fix to be deployed (X4): its regression test
    is expected to fail until then. Nothing when the bug flow's `mark_pending`
    or the deployment signal is off, when the bug is already done, or when it
    already carries the pending or the deployed label."""
    s = s or settings()
    if not is_bug(issue, s) or not s.get("mark_pending"):
        return False
    from core import deployment
    d = deployment.settings()
    labels = set(issue.get("labels") or [])
    if not deployment.enabled(d) or labels & {d["pending_label"], d["deployed_label"]} \
            or issue.get("done"):
        return False
    tracker.add_label(issue["key"], d["pending_label"])
    from integrations.tracker import add_markdown_comment
    add_markdown_comment(
        tracker, issue["key"],
        f"{MARKER} This bug's regression test asserts the expected result, so it fails "
        f"until the fix is live (`{d['pending_label']}`): its pull request reports that "
        f"failure as expected, and the run on main raises no second defect. When the fix "
        f"is deployed, add `{d['deployed_label']}` (or send the deployment signal) - from "
        f"then on a failure of the test is followed here, and a pass is said here too.")
    return True


def merged_note(tracker, key: str, s: dict | None = None) -> str | None:
    """At merge of a bug's regression test, instead of moving it to Done: the
    one comment that says the test is in and the bug stays open. None when
    the issue is not a bug of the flow (the caller moves it as a story)."""
    s = s or settings()
    try:
        issue = tracker.get_story(key)
    except Exception as e:                                         # noqa: BLE001
        logger.warning("%s: issue type not read (%s) - treated as a story.", key, e)
        return None
    if not is_bug(issue, s) or s.get("done_on_merge"):
        return None
    from core import deployment
    d = deployment.settings()
    waiting = deployment.is_pending(issue.get("labels"), d)
    body = (f"{MARKER} The regression test for this bug is merged. The bug is not closed by "
            f"the merge - the test is in, the fix may not be: close it when the fix is "
            f"verified. " + (f"It still waits for the fix (`{d['pending_label']}`): add "
                             f"`{d['deployed_label']}` when it is live." if waiting else
                             "A failure of the test on main is followed here."))
    try:
        if not any(MARKER in str(c) and "regression test for this bug is merged" in str(c)
                   for c in tracker.get_comments(key) or []):
            from integrations.tracker import add_markdown_comment
            add_markdown_comment(tracker, key, body)
    except Exception as e:                                         # noqa: BLE001
        logger.warning("%s: merge note not posted (%s).", key, e)
    return body
