"""A claim that something is NOT there survives into the code, and means it.

Agent 1 now writes a step asserting what a story removed is gone
(test_acceptance_coverage). These checks keep that step from being dropped by
Agent 2, emptied in its step definition, or satisfied by a blank page.

Written against a different application (a library) on purpose.
"""
from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from core.schemas import GeneratedFile, TestCase, TestStep
from validators.absence_claims import (
    absence_claims, absence_claims_missing, assertion_steps, negated_step, states_absence,
    states_exclusion, states_refusal, validate_absence_predicates_prove_their_page,
    validate_absence_steps_assert_absence,
)


def _gf(path, content):
    content = textwrap.dedent(content)
    if path.endswith(".py"):
        compile(content, path, "exec")             # a fixture that does not parse proves nothing
    return GeneratedFile(file_path=path, content=content, is_new_file=True, purpose="test")


# ─────────────────────────────────────────────────────────────
# Reading claims
# ─────────────────────────────────────────────────────────────
@pytest.mark.parametrize("text, absent", [
    ("The renewal-count field is not present on the loan page", True),
    ("No renewal-count field is shown", True),
    ("'Borrow it' is no longer shown", True),
    ("No button reads 'Borrow it'", True),
    ("The loan for 'Dune' is removed from the history", True),
    ("An error 'Card number is missing' is shown", False),        # quoted content is not the claim
    ("The loan shows a due date fourteen days later", False),
    ("The book page is never opened", False),
])
def test_states_absence(text, absent):
    assert states_absence(text) is absent


def test_exclusion_and_refusal_are_separate_questions():
    assert states_exclusion("Opening the old address shows a not-found page")
    assert states_exclusion("The book page is never opened")
    assert not states_absence("Opening the old address shows a not-found page")
    assert states_refusal("A sixth hold is rejected with an error")
    assert not states_refusal("The fifth hold is placed")


@pytest.mark.parametrize("step, negated", [
    ("I should not be signed in", True),
    ("no book cards should be shown", True),
    ('the history should not contain "{title}"', True),
    ("the renewal-count field should not be shown on the loan page", True),
    ("the renewal-count field is no longer shown", True),
    ("the page should say the card number is not valid", False),   # a message, not absence
    ('the error "Card is not valid" should be shown', False),
    ("I should remain on the catalogue page", False),
])
def test_negated_step(step, negated):
    assert negated_step(step) is negated


def test_claims_are_read_from_the_trackers_own_rendering():
    """Agent 1 writes through the tracker adapter; Agent 2 reads that text back.
    Pin that the two agree on the format."""
    from integrations.jira_client import JiraClient
    tc = TestCase(title="t", description="d", expected_outcome="o", steps=[
        TestStep(step_number=1, action="Open the loan page", expected_result="The loan page opens"),
        TestStep(step_number=2, action="Look for the renewal count",
                 expected_result="The renewal-count field is not present on the loan page")])
    rendered = JiraClient._format_test_case_description(tc)
    assert absence_claims(rendered) == ["The renewal-count field is not present on the loan page"]
    assert absence_claims(rendered.replace("_Expected:_", "*Expected:*")) == \
        ["The renewal-count field is not present on the loan page"]


# ─────────────────────────────────────────────────────────────
# 1. Claims carried into the scenario
# ─────────────────────────────────────────────────────────────
TC = {"key": "LIB-9", "summary": "Loan page offers no renewal count",
      "description": "# *Open the loan page*\n   _Expected:_ The loan page opens\n"
                     "# *Look*\n   _Expected:_ The renewal-count field is not present on the loan page\n"}

DROPPED = """\
  Scenario: Loan page offers no renewal count
    Given I am on the loan page for "Dune"
    Then the loan page should show the due date
"""
CARRIED = DROPPED + "    And the renewal-count field should not be shown on the loan page\n"


def test_a_scenario_that_drops_the_absence_step_is_rejected():
    errors = absence_claims_missing([TC], {"LIB-9": ("features/loans.feature", DROPPED)})
    assert len(errors) == 1 and errors[0].startswith("Absence claim error in 'features/loans.feature'")
    assert absence_claims_missing([TC], {"LIB-9": ("features/loans.feature", CARRIED)}) == []


def test_a_test_case_not_in_this_batch_is_not_judged():
    assert absence_claims_missing([TC], {}) == []


def test_an_and_after_a_when_is_not_an_assertion():
    text = ("  Scenario: s\n    Given x\n    When I open it\n"
            "    And I should not wait\n    Then it opens\n")
    assert assertion_steps(text) == ["it opens"]


def test_agent2_pairs_scenarios_before_and_after_markers_are_injected():
    from agents.agent2_coder import _absence_claim_errors, _inject_markers_into_feature
    feature = "Feature: Loans\n\n" + DROPPED
    errors = _absence_claim_errors([_gf("features/loans.feature", feature)], [TC])
    assert errors and "LIB-9" in errors[0]                             # paired by the injector
    marked = _inject_markers_into_feature("Feature: Loans\n\n" + CARRIED, [TC])
    assert "# JIRA: LIB-9" in marked
    assert _absence_claim_errors([_gf("features/loans.feature", marked)], [TC]) == []
    assert _absence_claim_errors([_gf("features/loans.feature", feature)], None) == []


def test_the_single_scenario_writer_retries_once_when_it_drops_the_claim(monkeypatch):
    from agents import agent2_coder
    monkeypatch.setattr(agent2_coder, "_build_readable_values_block", lambda: "")

    class LLM:
        def __init__(self):
            self.prompts = []

        def invoke_text(self, system_prompt, user_prompt):
            self.prompts.append(user_prompt)
            body = DROPPED if len(self.prompts) == 1 else CARRIED
            return "```gherkin\n# JIRA: LIB-9 (hash: x)\n" + body + "```"

    llm = LLM()
    text = agent2_coder._generate_single_scenario(llm, "features/loans.feature", TC, None, "")
    assert len(llm.prompts) == 2 and "should not be shown" in text
    assert "renewal-count field is not present" in llm.prompts[0]      # told up front
    assert "previous answer was rejected" in llm.prompts[1]


def test_the_single_scenario_writer_makes_one_call_when_there_is_no_claim(monkeypatch):
    from agents import agent2_coder
    monkeypatch.setattr(agent2_coder, "_build_readable_values_block", lambda: "")
    calls = []

    class LLM:
        def invoke_text(self, system_prompt, user_prompt):
            calls.append(user_prompt)
            return DROPPED

    tc = dict(TC, description="# *Open*\n   _Expected:_ The loan page opens\n")
    agent2_coder._generate_single_scenario(LLM(), "features/loans.feature", tc, None, "")
    assert len(calls) == 1


# ─────────────────────────────────────────────────────────────
# 2. A step worded as absence asserts absence
# ─────────────────────────────────────────────────────────────
def _steps(body):
    head = ('from pytest_bdd import then\n\n'
            '@then("the renewal-count field should not be shown on the loan page")\n'
            'def renewal_gone(loan_page):\n')
    return _gf("tests/step_defs/test_loans.py", head + textwrap.indent(textwrap.dedent(body), "    "))


@pytest.mark.parametrize("body", [
    "assert loan_page.is_renewal_count_absent()\n",
    "assert not loan_page.has_renewal_count()\n",
    "loan_page.wait_for_title(name, present=False)\n",
    "assert loan_page.count_renewals() == 0\n",
])
def test_bodies_that_answer_absence_pass(body):
    assert validate_absence_steps_assert_absence([_steps(body)]) == []


def test_a_body_that_only_checks_the_page_is_rejected():
    errors = validate_absence_steps_assert_absence([_steps("assert loan_page.is_loaded()\n")])
    assert len(errors) == 1 and errors[0].startswith("Absence step error in 'tests/step_defs/")


def test_a_page_object_method_that_answers_absence_counts_whatever_its_name(tmp_path):
    page = _gf("pages/loan_page.py", """\
        class LoanPage:
            def check_renewals(self) -> None:
                self.wait_for_row(self.sel("loan_rows"), "x", present=False)
    """)
    steps = _steps("loan_page.check_renewals()\n")
    assert validate_absence_steps_assert_absence([page, steps], tmp_path) == []


def test_the_committed_suite_passes():
    root = Path(__file__).resolve().parents[2]
    files = [_gf(str(p.relative_to(root)).replace("\\", "/"), p.read_text(encoding="utf-8"))
             for p in (root / "tests" / "step_defs").glob("*.py")]
    assert validate_absence_steps_assert_absence(files, root) == []


# ─────────────────────────────────────────────────────────────
# 3. Absence of a permanent element is proven on a loaded page
# ─────────────────────────────────────────────────────────────
@pytest.fixture
def project(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "config.yaml").write_text(
        "app_under_test:\n  inventory_file: inv.json\n", encoding="utf-8")
    (tmp_path / "inv.json").write_text(json.dumps({"pages": {"loan": {
        "page_object_class": "LoanPage", "elements": {"renewal_count": "#r", "due_date": "#d",
                                                      "saved_toast": "#t"},
        "conditional": ["saved_toast"]}}}), encoding="utf-8")
    (tmp_path / "pages").mkdir()
    return tmp_path


def _page(method):
    head = ('class LoanPage:\n'
            '    def is_loaded(self) -> bool:\n'
            '        return self.is_showing(self.sel("due_date"))\n\n')
    return _gf("pages/loan_page.py", head + textwrap.indent(textwrap.dedent(method), "    "))


def test_a_removal_check_without_a_page_proof_is_rejected(project):
    errors = validate_absence_predicates_prove_their_page([_page("""\
        def is_renewal_count_absent(self) -> bool:
            return self.is_gone(self.sel("renewal_count"))
    """)], project)
    assert len(errors) == 1 and "self.is_loaded() and self.is_gone" in errors[0]


@pytest.mark.parametrize("method", [
    """\
    def is_renewal_count_absent(self) -> bool:
        return self.is_loaded() and self.is_gone(self.sel("renewal_count"))
    """,
    """\
    def is_saved_toast_absent(self) -> bool:
        return self.is_gone(self.sel("saved_toast"))
    """,
])
def test_a_proven_page_or_a_conditional_element_passes(project, method):
    assert validate_absence_predicates_prove_their_page([_page(method)], project) == []


def test_committed_methods_are_left_alone(project):
    method = """\
        def is_renewal_count_absent(self) -> bool:
            return self.is_gone(self.sel("renewal_count"))
    """
    gf = _page(method)
    (project / "pages" / "loan_page.py").write_text(gf.content, encoding="utf-8")
    assert validate_absence_predicates_prove_their_page([gf], project) == []


def test_the_committed_page_objects_pass():
    root = Path(__file__).resolve().parents[2]
    files = [_gf(f"pages/{p.name}", p.read_text(encoding="utf-8"))
             for p in (root / "pages").glob("*.py")]
    assert validate_absence_predicates_prove_their_page(files, root) == []


def test_agent2_runs_the_checks_in_its_gate():
    import inspect
    from agents import agent2_coder
    collector = inspect.getsource(agent2_coder._collect_repairable_errors)
    assert "validate_absence_steps_assert_absence" in collector
    assert "validate_absence_predicates_prove_their_page" in collector
    for fn in (agent2_coder._attempt_step_coverage_repair, agent2_coder._validate_generated_files):
        assert "_absence_claim_errors(generated_files, test_cases)" in inspect.getsource(fn)


def test_the_coder_prompt_teaches_what_the_gate_accepts():
    root = Path(__file__).resolve().parents[2]
    text = (root / "prompts" / "agent2_coder_generate.md").read_text(encoding="utf-8")
    assert "return self.is_loaded() and self.is_gone(" in text
    assert "An expected result that says something is NOT there is a step of its own" in text
