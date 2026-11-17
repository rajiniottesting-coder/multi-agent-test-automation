"""A production bug gets a regression test (D3, core/bug_flow.py).

A bug a person raised - steps to reproduce, the expected result, the actual
one - goes through Agents 1 and 2 like a story: selected with the story
trigger label, held to its expected result, drafted as a regression test that
asserts the EXPECTED behaviour, marked awaiting its fix, and never closed by
the merge of its test. The triage's own defects are never taken. Off, a
project is exactly as before.
"""
from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from core import bug_flow
from core.schemas import CriterionCoverage, TestCase, TestCaseList, TestStep

for v in ("OPENAI_API_KEY", "JIRA_URL", "JIRA_EMAIL", "JIRA_API_TOKEN", "JIRA_PROJECT_KEY",
          "GITHUB_TOKEN", "GITHUB_REPO"):
    os.environ.setdefault(v, "stub")


REPORT_MD = """The cart total ignores the quantity.

**Steps to reproduce**
1. Open a product's details page
2. Set the quantity to 3 and add it to the cart
3. Open the cart
**Expected result**
- The cart line shows quantity 3
- The total is three times the price
**Actual result**
The total shows the price of one
"""

REPORT_WIKI = """h3. Steps to reproduce
# Open the cart
# Remove the only product

h3. Expected result
The cart says it is empty

h3. Actual result
An empty table is shown
"""


def _on(**over) -> dict:
    from core.ops_settings import DEFAULTS
    return {**DEFAULTS["bug_flow"], "enabled": True, **over}


@pytest.fixture
def flow_on(monkeypatch):
    s = _on()
    monkeypatch.setattr(bug_flow, "settings", lambda: dict(s))
    return s


# ── reading a bug report ──────────────────────────────────────────────

def test_the_expected_results_are_read_in_markdown(flow_on):
    assert bug_flow.expected_results(REPORT_MD) == [
        "The cart line shows quantity 3", "The total is three times the price"]
    assert bug_flow.steps_to_reproduce(REPORT_MD)[1] == "Set the quantity to 3 and add it to the cart"
    assert bug_flow.actual_results(REPORT_MD) == ["The total shows the price of one"]


def test_the_expected_results_are_read_in_jira_wiki_markup(flow_on):
    assert bug_flow.expected_results(REPORT_WIKI) == ["The cart says it is empty"]
    assert bug_flow.steps_to_reproduce(REPORT_WIKI) == ["Open the cart", "Remove the only product"]


def test_the_next_heading_ends_a_section_without_a_blank_line(flow_on):
    text = "Expected: the badge shows 2\nActual: the badge shows 1\n"
    assert bug_flow.expected_results(text) == ["the badge shows 2"]
    assert bug_flow.actual_results(text) == ["the badge shows 1"]


def test_a_bug_without_an_expected_result_is_not_ready(flow_on):
    why = bug_flow.readiness_problem({"description": "Steps to reproduce:\n1. Open it\n"})
    assert "no expected result" in why
    assert bug_flow.readiness_problem({"description": REPORT_MD}) == ""
    # An acceptance-criteria list is enough too.
    assert bug_flow.readiness_problem({"description": "Acceptance criteria:\n1. It works\n"}) == ""


def test_a_bug_is_held_to_its_expected_results(flow_on):
    from core.acceptance_coverage import extract_criteria
    found = extract_criteria("Cart total ignores quantity", REPORT_MD, "Bug")
    assert [(c.ref, c.source, c.mapped) for c in found] == [
        ("EXP1", "expected result", True), ("EXP2", "expected result", True)]
    # A story, and a bug with an acceptance-criteria list, are read as before.
    story = extract_criteria("t", "Acceptance criteria:\n1. It works\n", "Story")
    assert [c.ref for c in story] == ["AC1"]
    assert [c.ref for c in extract_criteria("t", "Acceptance criteria:\n1. It works\n", "Bug")] \
        == ["AC1"]
    assert extract_criteria("t", REPORT_MD, "Story") == extract_criteria("t", REPORT_MD)


def test_off_a_bug_is_read_as_before(monkeypatch):
    monkeypatch.setattr(bug_flow, "settings", lambda: _on(enabled=False))
    from core.acceptance_coverage import extract_criteria
    assert extract_criteria("t", REPORT_MD, "Bug") == extract_criteria("t", REPORT_MD)
    assert not bug_flow.is_bug({"issue_type": "Bug"})
    assert bug_flow.owner_types() == ["Story"]
    assert bug_flow.widened("Story") == ("Story", None)


def test_the_prompt_says_assert_the_expected_result(flow_on):
    block = bug_flow.prompt_block({"description": REPORT_MD})
    assert "BUG REPORT" in block and "Assert the EXPECTED result" in block
    assert "1. The cart line shows quantity 3" in block
    assert "The total shows the price of one" in block            # shown, never asserted
    assert "{" not in block


# ── selection and ownership ───────────────────────────────────────────

def test_a_story_selection_also_takes_bugs_but_not_the_triage_s_defects(flow_on):
    types, not_label = bug_flow.widened("Story")
    assert types == ["Story", "Bug"] and not_label == "ai-defect"
    assert bug_flow.widened("Bug") == ("Bug", None)
    assert bug_flow.widened("Task") == ("Task", None)
    assert bug_flow.widened(["Story", "Task"]) == (["Story", "Task"], None)


def _fake_jira(monkeypatch):
    from tests.sandbox.fake_jira import FakeJira, jira_client_over
    fake = FakeJira()
    return fake, jira_client_over(fake, monkeypatch)


def test_the_tracker_scan_finds_a_labelled_bug(flow_on, monkeypatch):
    fake, jc = _fake_jira(monkeypatch)
    story = fake.add("Story", "A story", labels=["ai-ready"], status="To Do")
    bug = fake.add("Bug", "A bug", labels=["ai-ready"], status="To Do")
    own = fake.add("Bug", "The triage's defect", labels=["ai-ready", "ai-defect"], status="To Do")
    fake.add("Task", "A task", labels=["ai-ready"], status="To Do")
    found = {s["key"] for s in jc.find_stories_to_process(
        {"issue_type": "Story", "required_labels": ["ai-ready"]})}
    assert found == {story, bug}
    assert own not in found
    # A selection of another type is not widened.
    assert {s["key"] for s in jc.find_stories_to_process(
        {"issue_type": "Bug", "required_labels": ["ai-ready"]})} == {bug, own}


def test_off_the_tracker_scan_takes_stories_only(monkeypatch):
    monkeypatch.setattr(bug_flow, "settings", lambda: _on(enabled=False))
    fake, jc = _fake_jira(monkeypatch)
    story = fake.add("Story", "A story", labels=["ai-ready"], status="To Do")
    fake.add("Bug", "A bug", labels=["ai-ready"], status="To Do")
    assert [s["key"] for s in jc.find_stories_to_process(
        {"issue_type": "Story", "required_labels": ["ai-ready"]})] == [story]


def test_the_issue_says_its_type_and_whether_it_is_done(flow_on, monkeypatch):
    fake, jc = _fake_jira(monkeypatch)
    bug = fake.add("Bug", "A bug", status="To Do")
    got = jc.get_story(bug)
    assert got["issue_type"] == "Bug" and got["done"] is False


def test_a_bug_owns_its_test_cases(flow_on, monkeypatch):
    fake, jc = _fake_jira(monkeypatch)
    bug = fake.add("Bug", "A bug", status="To Do")
    tc = fake.add("Test Case", "[Negative] Cart total counts the quantity")
    jc._create_link(bug, tc, "owns")
    assert jc.get_parent_story_key(tc) == bug
    monkeypatch.setattr(bug_flow, "settings", lambda: _on(enabled=False))
    assert jc.get_parent_story_key(tc) is None                    # as before: stories only


# ── Agent 1 drafts a regression test ─────────────────────────────────

def _tc(title, expected):
    return TestCase(title=title, description="d", steps=[
        TestStep(step_number=1, action="open the cart", expected_result=expected)],
        expected_outcome="done")


@pytest.fixture
def agent1_on_a_bug(flow_on, monkeypatch):
    from agents import agent1_analyst
    jira = MagicMock()
    jira.count_linked_test_cases.return_value = 0
    jira.get_impacted_test_cases.return_value = []
    jira.get_story.return_value = {"key": "PRJ-9", "summary": "Cart total ignores quantity",
                                   "description": REPORT_MD, "labels": ["ai-ready"],
                                   "components": [], "issue_type": "Bug", "done": False}
    jira.create_test_case.return_value = MagicMock(key="PRJ-10")
    seen = {}

    def draft(llm, prompt, criteria=None, existing=()):
        seen.update(prompt=prompt, criteria=criteria)
        return TestCaseList(story_summary="s", test_cases=[
            _tc("[Negative] Cart total counts the quantity", "the total is three times the price")],
            coverage=[CriterionCoverage(criterion="EXP1", covered_by=["[Negative] Cart total counts the quantity"]),
                      CriterionCoverage(criterion="EXP2", covered_by=["[Negative] Cart total counts the quantity"])])
    monkeypatch.setattr(agent1_analyst, "get_tracker", lambda: jira)
    monkeypatch.setattr(agent1_analyst, "_draft_test_cases", draft)
    monkeypatch.setattr(agent1_analyst, "LLMClient", lambda **k: MagicMock())
    monkeypatch.setattr(agent1_analyst, "existing_scenario_titles", lambda **k: set())
    from core import deployment
    monkeypatch.setattr(deployment, "settings", lambda: {
        "enabled": True, "story_type": "Story", "pending_label": "awaiting-deployment",
        "deployed_label": "deployed", "mark_on_handover": True})
    monkeypatch.setattr("core.usage_ledger.has_usage", lambda *a, **k: False)
    monkeypatch.setattr("core.usage_ledger.post_usage_to_story", lambda *a, **k: None)
    return agent1_analyst, jira, seen


def test_agent1_drafts_a_bug_as_a_regression_test(agent1_on_a_bug):
    agent1, jira, seen = agent1_on_a_bug
    result = agent1.run("PRJ-9")
    assert result["status"] == "tests_drafted"
    assert [c.ref for c in seen["criteria"]] == ["EXP1", "EXP2"]
    assert "This issue is a BUG REPORT" in seen["prompt"]
    # Its regression test fails until the fix is live: marked, said once.
    jira.add_label.assert_any_call("PRJ-9", "awaiting-deployment")
    assert any("[bug-flow]" in str(c) for c in jira.add_comment.call_args_list) or \
        any("[bug-flow]" in str(c) for c in jira.method_calls)


def test_a_bug_already_deployed_or_done_is_not_marked(flow_on, monkeypatch):
    from core import deployment
    monkeypatch.setattr(deployment, "settings", lambda: {
        "enabled": True, "story_type": "Story", "pending_label": "awaiting-deployment",
        "deployed_label": "deployed", "mark_on_handover": True})
    tracker = MagicMock()
    assert not bug_flow.mark_pending(tracker, {"key": "B-1", "issue_type": "Bug",
                                               "labels": ["deployed"]})
    assert not bug_flow.mark_pending(tracker, {"key": "B-1", "issue_type": "Bug", "done": True})
    assert not bug_flow.mark_pending(tracker, {"key": "S-1", "issue_type": "Story"})
    tracker.add_label.assert_not_called()


def test_agent1_hands_back_a_bug_with_no_expected_result(agent1_on_a_bug):
    agent1, jira, _seen = agent1_on_a_bug
    jira.get_story.return_value = {**jira.get_story.return_value,
                                   "description": "Steps to reproduce:\n1. Open the cart\n"}
    result = agent1.run("PRJ-9")
    assert result["status"] == "not_ready" and result["bug"] is True
    assert "Expected result" in agent1.NEEDS_A_PERSON_WHY["not_ready_bug"]
    jira.create_test_case.assert_not_called()


# ── at merge ──────────────────────────────────────────────────────────

class _Tracker:
    def __init__(self, issue):
        self.issue, self.comments = issue, []

    def get_story(self, key):
        return self.issue

    def get_comments(self, key):
        return list(self.comments)

    def add_comment(self, key, body):
        self.comments.append(body)


def test_merging_the_regression_test_does_not_close_the_bug(flow_on, monkeypatch):
    from core import deployment
    monkeypatch.setattr(deployment, "settings", lambda: {
        "enabled": True, "story_type": "Story", "pending_label": "awaiting-deployment",
        "deployed_label": "deployed", "mark_on_handover": True})
    t = _Tracker({"key": "B-1", "issue_type": "Bug", "labels": ["awaiting-deployment"]})
    note = bug_flow.merged_note(t, "B-1")
    assert "not closed by the merge" in note and "add `deployed`" in note
    bug_flow.merged_note(t, "B-1")
    assert len(t.comments) == 1                                    # said once
    assert bug_flow.merged_note(_Tracker({"issue_type": "Story"}), "S-1") is None


def test_close_merged_story_leaves_a_bug_open(flow_on, monkeypatch, capsys):
    import scripts.close_merged_story as cms
    moved = []
    monkeypatch.setattr(cms, "load_status_workflow", lambda: {"enabled": True, "on_merge": "Done"})
    monkeypatch.setattr(cms, "move_card_on_merge", lambda t, k: moved.append(k) or True)
    monkeypatch.setattr(cms, "get_tracker", lambda: _Tracker({"issue_type": "Bug", "labels": []}))
    monkeypatch.setattr("sys.argv", ["x", "--story", "B-1", "--merged", "true"])
    assert cms.main() == 0
    assert moved == [] and "a bug - not moved" in capsys.readouterr().out
    monkeypatch.setattr(cms, "get_tracker", lambda: _Tracker({"issue_type": "Story", "labels": []}))
    assert cms.main() == 0 and moved == ["B-1"]


def test_the_shipped_config_turns_the_bug_flow_on():
    import yaml
    from config.paths import CONFIG_YAML
    cfg = yaml.safe_load(CONFIG_YAML.read_text(encoding="utf-8"))
    assert cfg["bug_flow"]["enabled"] is True and cfg["bug_flow"]["done_on_merge"] is False
    from core.ops_settings import DEFAULTS
    assert DEFAULTS["bug_flow"]["enabled"] is False                # off unless a project opts in
