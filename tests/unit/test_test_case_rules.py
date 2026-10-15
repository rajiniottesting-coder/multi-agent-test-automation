"""Drafted test cases are checked before anything reaches the tracker.

Two rules (core/test_case_rules.py):
  - every test case stands alone: no "previous scenario", no "same session"
  - no absolute claim on a page the inventory marks persistent_state

Covered here: the rules on their own, Agent 1's normal mode (send back once,
then stop before any write), and impact-aware mode (same rules on revised and
new test cases). Generic names only; no network, no model.
"""
import os
from unittest.mock import MagicMock, patch

import pytest

from core.schemas import (
    ImpactAwareDraft,
    TestCase,
    TestCaseList,
    TestCaseRevision,
    TestStep,
)
from core.test_case_rules import (
    draft_problems,
    persistent_pages,
    rejection_note,
    test_case_problems,
)

for v in ("OPENAI_API_KEY", "JIRA_URL", "JIRA_EMAIL", "JIRA_API_TOKEN",
          "JIRA_PROJECT_KEY", "GITHUB_TOKEN", "GITHUB_REPO"):
    os.environ.setdefault(v, "stub")

for _cls in (TestCase, TestCaseList, TestCaseRevision, TestStep):
    _cls.__test__ = False
test_case_problems.__test__ = False

INVENTORY = {"pages": {
    "saved_items": {"url": "/saved_items", "persistent_state": True},
    "widget_detail": {"url": "/widget_detail/{id}"},
    "search": {"url": "/search", "persistent_state": False},
}}
PERSISTENT = persistent_pages(INVENTORY)


def _tc(title="[Positive] Add a widget", pre=(), action="Open a widget",
        expected="The widget is shown", outcome="It works"):
    return TestCase(title=title, description="d", priority="High", test_type="Positive",
                    preconditions=list(pre),
                    steps=[TestStep(step_number=1, action=action, expected_result=expected)],
                    expected_outcome=outcome, test_data=None)


GOOD = _tc(pre=["Signed in as the shopper role"], action="Add 'Blue Widget' to saved items",
           expected="Saved items shows a row for 'Blue Widget' with quantity 2",
           outcome="The row for 'Blue Widget' is present in saved items with quantity 2.")
BAD_DEPENDENT = _tc(pre=["Saved items already holds 'Blue Widget', added as in the previous scenario."])
BAD_ABSOLUTE = _tc(outcome="A single row for 'Blue Widget' is shown in saved items, rather than two separate rows.")


# ─────────────────────────────────────────────────────────────
# The rules
# ─────────────────────────────────────────────────────────────

def test_only_persistent_pages_are_collected_with_their_names():
    assert PERSISTENT == {"saved_items": ["/saved_items", "saved items", "saved_items"]}


@pytest.mark.parametrize("text", [
    "added via the detail pages as in the previous scenario",
    "Continue in the same incognito session",
    "Run this in the same browser session as before",
    "Continuing from the previous test, open the list",
    "The items left from an earlier run are visible",
    "depends on the prior test case",
])
def test_dependency_phrases_are_found_in_any_field(text):
    assert test_case_problems(_tc(action=text), PERSISTENT)
    assert test_case_problems(_tc(pre=[text]), PERSISTENT)


@pytest.mark.parametrize("text", [
    "Saved items contains exactly one row",
    "Only 'Blue Widget' remains in saved items",
    "Saved items is empty",
    "A single row is shown in saved items",
    "Saved items shows 2 rows",
    "No other row appears on /saved_items",
    "saved items lists it once rather than two rows",
])
def test_absolute_claims_on_a_persistent_page_are_found(text):
    assert test_case_problems(_tc(expected=text), PERSISTENT)


def test_relative_claims_and_other_pages_are_fine():
    assert test_case_problems(GOOD, PERSISTENT) == []
    assert test_case_problems(_tc(expected="Search shows exactly one result"), PERSISTENT) == []
    assert test_case_problems(_tc(expected="The 'Blue Widget' row is gone from saved items"),
                              PERSISTENT) == []


def test_a_step_action_may_mention_counts_only_expectations_are_checked():
    assert test_case_problems(_tc(action="Remove the only 'Blue Widget' row in saved items"),
                              PERSISTENT) == []


def test_without_an_inventory_only_dependencies_are_checked():
    assert test_case_problems(BAD_ABSOLUTE, {}) == []
    assert test_case_problems(BAD_DEPENDENT, {})


def test_problems_name_the_test_case_and_say_how_to_fix_it():
    [p] = test_case_problems(BAD_DEPENDENT, PERSISTENT)
    assert p.startswith("'[Positive] Add a widget':") and "fresh browser session" in p
    [p] = test_case_problems(BAD_ABSOLUTE, PERSISTENT)
    assert "saved_items page" in p and "relative to what this test did" in p


def test_non_text_fields_are_skipped():
    assert test_case_problems(MagicMock(), PERSISTENT) == []
    assert draft_problems(MagicMock(), PERSISTENT) == []


def test_rejection_note_lists_every_problem():
    note = rejection_note(["one", "two"])
    assert "# Your previous answer was rejected" in note and "- one\n- two" in note


# ─────────────────────────────────────────────────────────────
# Agent 1, normal mode
# ─────────────────────────────────────────────────────────────

@pytest.fixture
def agent1():
    from agents import agent1_analyst
    jira = MagicMock()
    jira.count_linked_test_cases.return_value = 0
    jira.get_impacted_test_cases.return_value = []
    jira.get_story.return_value = {"summary": "Save widgets", "description": "A shopper saves widgets"}
    jira.create_test_case.side_effect = lambda tc, parent_story_key: MagicMock(key="X-9")
    llm = MagicMock()
    with patch.object(agent1_analyst, "get_tracker", return_value=jira), \
         patch.object(agent1_analyst, "LLMClient", return_value=llm), \
         patch.object(agent1_analyst, "load_prompt", return_value="prompt {story_text}"), \
         patch("core.test_case_rules.load_persistent_pages", return_value=PERSISTENT):
        yield jira, llm, agent1_analyst.run


def _list(*cases):
    return TestCaseList(story_summary="s", test_cases=list(cases))


def test_a_clean_draft_is_written_after_one_call(agent1):
    jira, llm, run = agent1
    llm.invoke_structured.return_value = _list(GOOD)
    run("X-1")
    assert llm.invoke_structured.call_count == 1
    assert jira.create_test_case.call_count == 1


def test_a_bad_draft_is_sent_back_with_the_problems_and_the_fix_is_written(agent1):
    jira, llm, run = agent1
    llm.invoke_structured.side_effect = [_list(GOOD, BAD_DEPENDENT), _list(GOOD, GOOD)]
    run("X-1")
    retry_prompt = llm.invoke_structured.call_args_list[1].kwargs["user_prompt"]
    assert "# Your previous answer was rejected" in retry_prompt
    assert "previous scenario" in retry_prompt
    assert jira.create_test_case.call_count == 2


def test_a_draft_bad_twice_stops_before_any_write(agent1):
    jira, llm, run = agent1
    llm.invoke_structured.side_effect = [_list(BAD_ABSOLUTE), _list(BAD_ABSOLUTE)]
    with pytest.raises(ValueError, match="rejected twice; nothing was written"):
        run("X-1")
    jira.create_test_case.assert_not_called()
    jira.add_label.assert_not_called()
    jira.remove_label.assert_not_called()


# ─────────────────────────────────────────────────────────────
# Agent 1, impact-aware mode
# ─────────────────────────────────────────────────────────────

def _impact(revised, new=()):
    return ImpactAwareDraft(story_summary="s",
                            revisions=[TestCaseRevision(key="X-11", revised=revised, change_note="n")],
                            new_test_cases=list(new))


def test_impact_aware_revisions_and_new_cases_follow_the_same_rules():
    from agents.agent1_impact import validate_draft
    assert validate_draft(_impact(GOOD), {"X-11"}, set(), PERSISTENT) == ([], [])
    errors, _ = validate_draft(_impact(BAD_ABSOLUTE), {"X-11"}, set(), PERSISTENT)
    assert any("saved_items page" in e for e in errors)
    errors, _ = validate_draft(_impact(GOOD, [_tc(title="[Edge] Other", pre=BAD_DEPENDENT.preconditions)]),
                               {"X-11"}, set(), PERSISTENT)
    assert any("'[Edge] Other'" in e for e in errors)


def test_impact_aware_draft_bad_twice_raises():
    from agents import agent1_impact
    llm = MagicMock()
    llm.invoke_structured.return_value = _impact(BAD_DEPENDENT)
    with patch.object(agent1_impact, "load_persistent_pages", return_value=PERSISTENT), \
         pytest.raises(ValueError, match="rejected twice"):
        agent1_impact._draft(llm, "p", {"X-11"}, set())
    assert "previous scenario" in llm.invoke_structured.call_args_list[1].kwargs["user_prompt"]


# ─────────────────────────────────────────────────────────────
# The rule must accept its own remedy
# ─────────────────────────────────────────────────────────────
# The rejection tells the model: "what it added is present, or what it removed
# is gone". A rule that then rejects that very phrasing can never be satisfied:
# validation story SCRUM-187 was rejected twice for "No row for '<item>' is
# present in the cart" - the relative absence the remedy asked for.

@pytest.mark.parametrize("text", [
    "No row for 'Blue Widget' is present in saved items",
    "No rows for 'Blue Widget' remain in saved items",
    "Saved items shows no row named 'Blue Widget'",
    "Saved items has no row containing 'Blue Widget' afterward",
    "The 'Blue Widget' row is gone from saved items",
    "Saved items still shows a row for 'Blue Widget'",
])
def test_named_presence_or_absence_is_relative_and_accepted(text):
    assert test_case_problems(_tc(expected=text), PERSISTENT) == []


@pytest.mark.parametrize("text", [
    "Saved items has no rows",
    "No rows are shown in saved items",
    "No other rows appear in saved items",
    "No other row for 'Blue Widget' appears in saved items",
])
def test_whole_page_absence_is_still_absolute(text):
    assert test_case_problems(_tc(expected=text), PERSISTENT)


def test_the_example_in_the_remedy_passes_the_rule():
    [p] = test_case_problems(BAD_ABSOLUTE, PERSISTENT)
    example = p.split("(for example: \"", 1)[1].split("\")", 1)[0]
    sentence = example.replace("<item>", "Blue Widget") + " in saved items"
    assert test_case_problems(_tc(expected=sentence), PERSISTENT) == []
