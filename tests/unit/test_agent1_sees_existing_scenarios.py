"""Agent 1's draft sees the scenarios that already exist: the prompt lists
them, a new test case titled as an existing scenario is sent back, and an
unchanged criterion may cite an existing scenario.
"""

from __future__ import annotations

from pathlib import Path
import pytest
from core.schemas import CriterionCoverage, TestCase, TestCaseList, TestStep


ROOT = Path(__file__).resolve().parents[2]


def _tc(title, *expected):
    return TestCase(title=title, description="d", steps=[
        TestStep(step_number=i, action=f"do {i}", expected_result=e)
        for i, e in enumerate(expected, 1)], expected_outcome="done")


def test_a_new_test_case_titled_as_an_existing_scenario_is_sent_back():
    from agents.agent1_analyst import repeats_of_existing
    found = repeats_of_existing([_tc("[Positive] Visitor sends the form", "sent"),
                                 _tc("[Negative] Empty field is refused", "refused")],
                                {"visitor sends the form"})
    assert len(found) == 1 and "repeats an existing scenario" in found[0]


def test_an_unchanged_criterion_may_cite_an_existing_scenario(monkeypatch):
    from agents import agent1_analyst
    from core.acceptance_coverage import extract_criteria
    monkeypatch.setattr("core.test_case_rules.load_persistent_pages", lambda: {})
    criteria = extract_criteria("Form rule", "Acceptance criteria:\n1. The form still sends "
                                "as before.\n2. An empty title is refused.")
    draft = TestCaseList(story_summary="s",
                         test_cases=[_tc("[Negative] Empty title is refused",
                                         "the form is refused: no confirmation is shown")],
                         coverage=[CriterionCoverage(criterion="AC1",
                                                     covered_by=["visitor sends the form"]),
                                   CriterionCoverage(criterion="AC2",
                                                     covered_by=["[Negative] Empty title is refused"])])

    class LLM:
        def invoke_structured(self, **kw):
            return draft
    assert agent1_analyst._draft_test_cases(LLM(), "P", criteria,
                                            {"visitor sends the form"}) is draft


def test_the_draft_check_sends_a_copy_back(monkeypatch):
    from agents import agent1_analyst
    from core.test_case_rules import DraftRejected
    monkeypatch.setattr("core.test_case_rules.load_persistent_pages", lambda: {})
    copy = TestCaseList(story_summary="s", test_cases=[_tc("[Positive] Visitor sends the form", "sent")])

    class LLM:
        def invoke_structured(self, **kw):
            return copy
    with pytest.raises(DraftRejected, match="repeats an existing scenario"):
        agent1_analyst._draft_test_cases(LLM(), "P", None, {"visitor sends the form"})


def test_the_prompt_lists_the_existing_scenarios():
    prompt = (ROOT / "prompts" / "agent1_analyst.md").read_text(encoding="utf-8")
    assert "{existing_titles_block}" in prompt and "# Scenarios that already exist" in prompt
    src = (ROOT / "agents" / "agent1_analyst.py").read_text(encoding="utf-8")
    assert '"{existing_titles_block}"' in src
