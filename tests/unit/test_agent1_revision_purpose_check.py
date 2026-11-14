"""Agent 1's revision of a test case for a change story is flagged when it
changes the test's purpose or repeats another scenario, and passes when it
keeps its purpose.
"""

from core.schemas import ImpactAwareDraft, TestCase, TestCaseRevision, TestStep


def _case(title):
    return TestCase(title=title, description="d", priority="High", test_type="Positive",
                    preconditions=[], steps=[TestStep(step_number=1, action="a",
                                                      expected_result="b")],
                    expected_outcome="ok", test_data=None)


def _validate(new_title, existing=frozenset()):
    from agents.agent1_impact import validate_draft
    draft = ImpactAwareDraft(story_summary="s", new_test_cases=[], revisions=[
        TestCaseRevision(key="AB-1", revised=_case(new_title), change_note="n")])
    return validate_draft(draft, {"AB-1"}, set(existing), {},
                          {"AB-1": "[Positive] Choose a size and confirm the size in the basket"})


def test_a_revision_that_changes_its_purpose_is_flagged():
    errors, near = _validate("[Positive] Add the same item three times and see the count rise")
    assert not errors and any("changed its purpose" in n for n in near)


def test_a_revision_that_keeps_its_purpose_is_not_flagged():
    _e, near = _validate("[Positive] Choose a size and confirm the chosen size in the basket")
    assert not near


def test_a_revision_close_to_another_scenario_is_flagged():
    from agents.agent1_impact import _norm
    other = _norm("Choose a size and confirm the size shown in the basket view")
    _e, near = _validate("[Positive] Choose a size and confirm the size shown in the basket",
                         {other})
    assert any("close to an existing scenario" in n for n in near)
