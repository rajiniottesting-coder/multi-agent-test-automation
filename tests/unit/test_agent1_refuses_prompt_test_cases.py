"""A drafted test case about the prompt (instead of the application) is sent
back; an absence on the application is not about the prompt; both prompts say
a new thing is new.
"""

from __future__ import annotations

from pathlib import Path
import pytest


ROOT = Path(__file__).resolve().parents[2]


def _case(title, *expected):
    from core.schemas import TestCase, TestStep
    return TestCase(title=title, description="d", expected_outcome="done", steps=[
        TestStep(step_number=i, action=f"do {i}", expected_result=e)
        for i, e in enumerate(expected, 1)])


@pytest.mark.parametrize("title, expected", [
    ("[Negative] The list page and its search are not defined in the Application Under Test",
     "the page opens"),
    ("[Negative] Search", "the search box is not described in the application context"),
    ("[Negative] Search", "the filter is not present in the app notes"),
])
def test_a_test_case_about_the_prompt_is_refused(title, expected):
    from core.test_case_rules import test_case_problems
    problems = test_case_problems(_case(title, expected))
    assert problems and "tests what the prompt describes" in problems[0]


@pytest.mark.parametrize("expected", [
    "the search box is not present on the page",
    "the product is not available in the inventory",
    "no row for 'Item' is present",
])
def test_absence_on_the_application_is_not_about_the_prompt(expected):
    from core.test_case_rules import test_case_problems
    assert not any("tests what the prompt" in p
                   for p in test_case_problems(_case("[Negative] Gone", expected)))


def test_both_prompts_say_a_new_thing_is_new():
    for name in ("agent1_analyst.md", "agent1_impact_aware.md"):
        text = (ROOT / "prompts" / name).read_text(encoding="utf-8")
        assert "never write a test case stating that something is not defined" in text
