"""Agent 2's coverage audit: what a generated scenario leaves out of its test
case (an expected result, an implied check) is named in a note - it never stops
the run, and it runs after the gate and before the pull request.
"""

from __future__ import annotations


def _batch_with_marked_scenario():
    from core.schemas import GeneratedFile
    return [GeneratedFile(file_path="features/reports.feature", content=(
        "Feature: Reports\n\n  Background:\n    Given I am on the home page\n\n"
        "  # JIRA: AB-1 (hash: 00000000) owner: AB-9\n"
        "  Scenario: Open the reports page\n    When I open reports\n"
        "    Then the reports heading is shown\n"))]


def test_a_scenario_that_leaves_out_an_expected_result_is_named():
    from agents import agent2_coverage as cov
    seen = {}

    class LLM:
        def invoke_structured(self, system_prompt, user_prompt, output_schema):
            seen["prompt"] = user_prompt
            return cov.CoverageAudit(cases=[
                cov.CaseCheck(key="AB-1", not_checked=["a contact section with an email address"]),
                cov.CaseCheck(key="AB-7", not_checked=["not in this batch"])])
    cases = [{"key": "AB-1", "summary": "[Positive] Open reports",
              "description": "1. Open reports\nExpected: heading; a contact section with an email"},
             {"key": "AB-2", "summary": "no scenario", "description": "x"}]
    (gap,) = cov.audit_partial(LLM(), _batch_with_marked_scenario(), cases, "rules")
    assert gap.key == "AB-1" and gap.blocking is False
    assert "does not check: a contact section with an email address" in gap.reason
    assert "Given I am on the home page" in seen["prompt"], "the Background is judged too"
    assert "AB-2" not in seen["prompt"], "a test case with no scenario is not asked about"
    section = cov.pr_section([gap], [], {})
    assert "Covered, but needing a person" in section and "AB-1" in section


def test_the_audit_reads_implied_checks_and_its_note_asks_for_a_look_first():
    """F47: 'each title is a link' was reported as not checking 'the page lists the
    test cases'; the note then told the person to add an inventory element."""
    from agents import agent2_coder as a2
    from agents import agent2_coverage as cov
    rules = (a2.PROMPTS_DIR / "agent2_coverage_audit.md").read_text(encoding="utf-8")
    assert "every item of a list" in rules and "acts on an element" in rules
    # 11 Nov 2026: a section's email link checked was still listed as "the
    # section showing an email address" not checked - the rule names sections.
    assert "checked inside a section checks that the section is shown" in rules

    class LLM:
        def invoke_structured(self, **k):
            return cov.CoverageAudit(cases=[cov.CaseCheck(key="AB-1", not_checked=["x"])])
    (gap,) = cov.audit_partial(LLM(), _batch_with_marked_scenario(),
                               [{"key": "AB-1", "summary": "s", "description": "d"}], "r")
    assert "check the scenario first" in gap.reason
    assert gap.reason.index("check the scenario first") < gap.reason.index("inventory lacks")


def test_the_audit_never_stops_the_run():
    from agents import agent2_coverage as cov

    class Down:
        def invoke_structured(self, **k):
            raise RuntimeError("model down")
    assert cov.audit_partial(Down(), _batch_with_marked_scenario(), [{"key": "AB-1"}], "r") == []
    called = []

    class Never:
        def invoke_structured(self, **k):
            called.append(1)
    assert cov.audit_partial(Never(), _batch_with_marked_scenario(), [{"key": "AB-5"}], "r") == []
    assert called == [], "nothing to judge, no call"

    class Other:
        def invoke_structured(self, **k):
            return object()                     # an answer of another shape
    assert cov.audit_partial(Other(), _batch_with_marked_scenario(), [{"key": "AB-1"}], "r") == []


def test_agent2_runs_the_audit_after_the_gate_and_before_the_pull_request():
    import inspect
    import agents.agent2_coder as a2
    src = inspect.getsource(a2.run)
    assert src.index("_validate_generated_files(generated_files") < src.index("audit_partial(") \
        < src.index("pr_body_with_footer += agent2_coverage.pr_section")
    assert (a2.PROMPTS_DIR / "agent2_coverage_audit.md").is_file()
