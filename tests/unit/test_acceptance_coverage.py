"""Agent 1 must verify every acceptance criterion with a test that can FAIL.

Regression for the "remove a field" validation story: the change removed a
field, the revised tests simply stopped using it, nothing asserted it was gone,
and every test passed against an application that still had it.

Written against a different application (a library) on purpose: the rule is
plain English about requirements, so it must hold for any application.
"""
from __future__ import annotations

import pytest

from core.acceptance_coverage import (
    LENIENT, RULE, STRICT, coverage_problems, criteria_block, extract_criteria,
    index_cases, obligation, parse_acceptance_criteria, removed_object, render_coverage,
)
from core.schemas import (CriterionCoverage, ImpactAwareDraft, TestCase, TestCaseList,
                          TestCaseRevision, TestStep)


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────
def _tc(title, *expected, data=None):
    return TestCase(title=title, description="d", steps=[
        TestStep(step_number=i, action=f"do {i}", expected_result=e)
        for i, e in enumerate(expected, 1)], expected_outcome="done", test_data=data)


def _cov(ref, *cases, how=""):
    return CriterionCoverage(criterion=ref, covered_by=list(cases), how_verified=how)


STORY_MD = """As the head librarian, I want every loan to last fourteen days.

**Acceptance criteria:**

1. The loan page no longer offers a renewal-count field.
2. Each loan shows a due date fourteen days after it was borrowed.
3. On the catalogue page, each book card's own 'Borrow' button also starts a loan, without opening the book page.

"""
STORY_WIKI = """As the head librarian, I want every loan to last fourteen days.

*Acceptance criteria:*

# The loan page no longer offers a renewal-count field.
# Each loan shows a due date fourteen days after it was borrowed.
# On the catalogue page, each book card's own 'Borrow' button also starts a loan, without opening the book page.
"""
TITLE = "Remove the renewal choice: every loan lasts fourteen days"


# ─────────────────────────────────────────────────────────────
# Reading the criteria
# ─────────────────────────────────────────────────────────────
@pytest.mark.parametrize("text", [STORY_MD, STORY_WIKI])
def test_criteria_are_read_from_markdown_and_wiki_markup(text):
    items = parse_acceptance_criteria(text)
    assert len(items) == 3
    assert items[0] == "The loan page no longer offers a renewal-count field."


def test_bullets_gherkin_and_continuation_lines():
    text = ("h3. Acceptance Criteria\n"
            "* A member can reserve a book\n"
            "  that is on loan\n"
            "* Given a member with five holds\n"
            "  When they place another hold\n"
            "  Then it is rejected\n\n"
            "h3. Notes\n* not a criterion\n")
    items = parse_acceptance_criteria(text)
    assert items == ["A member can reserve a book that is on loan",
                     "Given a member with five holds When they place another hold Then it is rejected"]


def test_no_heading_means_no_parsed_criteria_only_removal_sentences():
    found = extract_criteria("Hide the fines column", "Members find the fines column confusing.")
    assert [(c.ref, c.obligation, c.mapped) for c in found] == [("TITLE", STRICT, False)]
    assert extract_criteria("Show a reading list", "Members can keep a reading list.") == []


@pytest.mark.parametrize("text, tier", [
    ("The loan page no longer offers a renewal-count field.", STRICT),
    ("The 'Borrow' button is labelled 'Reserve' instead of 'Borrow'.", STRICT),
    ("Borrowing a book opens the loan page directly; no confirmation dialog is shown.", STRICT),
    ("The fines column is hidden from members.", STRICT),
    ("A returned loan can be deleted from the history.", STRICT),
    ("Only librarians can delete a book.", LENIENT),
    ("A member cannot borrow a reference book.", LENIENT),
    ("A member can hold at most 5 books.", RULE),
    ("The library card number is required and must be 10 digits.", RULE),
    ("Searching by author returns that author's books.", None),
    ("None of this requires the member to sign in.", None),
])
def test_obligation_by_wording(text, tier):
    assert obligation(text) == tier


def test_restrictions_and_rules_only_count_in_explicit_criteria():
    assert obligation("Members cannot always find this.", explicit=False) is None
    assert obligation("It takes at least a day.", explicit=False) is None


def test_removed_object_names_the_thing_removed():
    assert set(removed_object("The loan page no longer offers a renewal-count field.").values()) \
        == {"renewal-count"}
    assert set(removed_object("no confirmation dialog is shown").values()) == {"confirmation", "dialog"}
    assert set(removed_object("labels it 'Reserve' instead of 'Borrow it'").values()) == {"borrow"}
    assert set(removed_object("A loan can be removed, leaving the history short").values()) == {"loan"}


# ─────────────────────────────────────────────────────────────
# The regression
# ─────────────────────────────────────────────────────────────
CRITERIA = extract_criteria(TITLE, STORY_WIKI)

REVISED_ONLY = _tc("[Positive] Borrow a book and see its due date",
                   "The loan page opens", "The due date is fourteen days later")
LISTING = _tc("[Positive] Borrow from the catalogue card",
              "The member stays on the catalogue; the book page is never opened",
              "The loan shows a due date fourteen days later")
ABSENCE = _tc("[Positive] The loan page offers no renewal count",
              "The loan page opens", "The renewal-count field is not present on the loan page")


def test_the_original_bug_is_rejected():
    """Revised tests stop using the field, one new test for the listing - and
    nothing says the field is gone."""
    coverage = [_cov("AC1", REVISED_ONLY.title), _cov("AC2", REVISED_ONLY.title),
                _cov("AC3", LISTING.title)]
    problems = coverage_problems(CRITERIA, coverage, index_cases([], [REVISED_ONLY, LISTING]))
    assert len(problems) == 1 and problems[0].startswith("AC1 ")
    assert "OBSERVE that it is gone" in problems[0]


def test_a_test_asserting_the_field_is_gone_satisfies_it():
    coverage = [_cov("AC1", ABSENCE.title), _cov("AC2", REVISED_ONLY.title),
                _cov("AC3", LISTING.title)]
    assert coverage_problems(CRITERIA, coverage,
                             index_cases([], [REVISED_ONLY, LISTING, ABSENCE])) == []


def test_an_absence_step_about_something_else_does_not_count():
    other = _tc("Borrow without the book page",
                "The book page is not shown", "The loan is listed")
    problems = coverage_problems(CRITERIA, [_cov("AC1", other.title), _cov("AC2", other.title),
                                            _cov("AC3", other.title)],
                                 index_cases([], [other]))
    assert any("renewal-count" in p for p in problems)


def test_every_criterion_must_be_in_the_map_and_cite_a_real_test():
    problems = coverage_problems(CRITERIA, [_cov("AC1", ABSENCE.title), _cov("AC2", "Nope")],
                                 index_cases([], [ABSENCE]))
    assert any(p.startswith("coverage for AC2 cites 'Nope'") for p in problems)
    assert any(p.startswith("AC3 ") and "not in the coverage map" in p for p in problems)


def test_criterion_refs_are_matched_loosely():
    coverage = [_cov("1", ABSENCE.title), _cov("AC 2: due date", REVISED_ONLY.title),
                _cov("AC3 - catalogue", LISTING.title)]
    assert coverage_problems(CRITERIA, coverage,
                             index_cases([], [REVISED_ONLY, LISTING, ABSENCE])) == []


def test_a_story_without_criteria_and_without_a_map_is_unchanged():
    assert coverage_problems([], [], index_cases([], [REVISED_ONLY])) == []


# ─────────────────────────────────────────────────────────────
# The other real use cases
# ─────────────────────────────────────────────────────────────
def _one(text):
    return extract_criteria("t", f"Acceptance criteria:\n1. {text}\n")


def test_rename_needs_the_old_wording_gone():
    crit = _one("Every book card labels the action 'Reserve' instead of 'Borrow it'.")
    new_only = _tc("Reserve label", "The card shows 'Reserve'")
    both = _tc("Reserve label", "The card shows 'Reserve'", "No button reads 'Borrow it'")
    assert coverage_problems(crit, [_cov("AC1", new_only.title)], index_cases([], [new_only]))
    assert coverage_problems(crit, [_cov("AC1", both.title)], index_cases([], [both])) == []


def test_restriction_needs_the_refusal():
    crit = _one("Only librarians can delete a book.")
    happy = _tc("Librarian deletes", "The book is deleted")
    refused = _tc("Member refused", "The member sees an access denied message")
    assert coverage_problems(crit, [_cov("AC1", happy.title)], index_cases([], [happy]))
    assert coverage_problems(crit, [_cov("AC1", happy.title, refused.title)],
                             index_cases([], [happy, refused])) == []


def test_a_rule_needs_the_violation_rejected():
    crit = _one("A member can hold at most 5 books.")
    happy = _tc("Five holds", "The fifth hold is placed")
    both = _tc("Hold limit", "The fifth hold is placed", "A sixth hold is rejected with an error")
    problems = coverage_problems(crit, [_cov("AC1", happy.title)], index_cases([], [happy]))
    assert problems and "BOTH sides" in problems[0]
    assert coverage_problems(crit, [_cov("AC1", both.title)], index_cases([], [both])) == []


def test_a_deleted_item_may_be_named_by_its_test_data():
    crit = _one("A returned loan can be deleted from the history.")
    named = _tc("Delete a loan", "No row for 'Dune' is present in the history",
                data={"book": "Dune"})
    assert coverage_problems(crit, [_cov("AC1", named.title)], index_cases([], [named])) == []


def test_a_removed_page_may_be_proven_unreachable():
    crit = _one("The old catalogue page is removed.")
    gone = _tc("Old catalogue gone", "No menu entry leads to the old catalogue",
               "Opening the old catalogue address shows a not-found page")
    assert coverage_problems(crit, [_cov("AC1", gone.title)], index_cases([], [gone])) == []


# ─────────────────────────────────────────────────────────────
# Impact-aware citations
# ─────────────────────────────────────────────────────────────
def test_an_existing_scenario_covers_only_a_criterion_without_an_obligation():
    existing = ["borrowing a book twice keeps one loan"]
    index = index_cases([("LIB-7", REVISED_ONLY)], [LISTING], existing)
    ok = [_cov("AC1", "LIB-7"), _cov("AC2", "Borrowing a book twice keeps one loan"),
          _cov("AC3", LISTING.title)]
    problems = coverage_problems(CRITERIA, ok, index)
    assert len(problems) == 1 and problems[0].startswith("AC1 ")           # LIB-7 has no absence step
    only_existing = [_cov("AC1", "Borrowing a book twice keeps one loan"),
                     _cov("AC2", "LIB-7"), _cov("AC3", LISTING.title)]
    problems = coverage_problems(CRITERIA, only_existing, index)
    assert any("Only existing scenarios are cited" in p for p in problems)


def test_a_revision_cited_by_key_counts_when_it_carries_the_step():
    revised = _tc("Borrow and check the loan page", "The loan page opens",
                  "The renewal-count field is no longer shown")
    index = index_cases([("LIB-7", revised)], [LISTING])
    coverage = [_cov("AC1", "LIB-7 (Borrow and check the loan page)"), _cov("AC2", "LIB-7"),
                _cov("AC3", LISTING.title)]
    assert coverage_problems(CRITERIA, coverage, index) == []


# ─────────────────────────────────────────────────────────────
# What the model and the reviewer see
# ─────────────────────────────────────────────────────────────
def test_the_prompt_marks_each_obligation():
    block = criteria_block(CRITERIA)
    assert "- AC1: The loan page no longer offers a renewal-count field." in block
    assert "ABSENT" in block.splitlines()[0]
    assert "(No acceptance-criteria list" in criteria_block([])


def test_the_coverage_comment_names_keys_and_titles():
    index = index_cases([("LIB-7", REVISED_ONLY)], [ABSENCE])
    lines = render_coverage(CRITERIA, [_cov("AC1", ABSENCE.title, how="step 2"),
                                       _cov("AC2", "LIB-7")], index)
    assert lines[0].startswith("- AC1 The loan page no longer offers") and "| step 2" in lines[0]
    assert lines[1].endswith("-> LIB-7")


# ─────────────────────────────────────────────────────────────
# Agent 1, both modes
# ─────────────────────────────────────────────────────────────
class _FakeLLM:
    def __init__(self, *answers):
        self.answers, self.prompts = list(answers), []

    def invoke_structured(self, system_prompt, user_prompt, output_schema):
        self.prompts.append(user_prompt)
        return self.answers.pop(0)


def test_agent1_sends_the_bug_back_once_and_accepts_the_fix(monkeypatch):
    from agents import agent1_analyst
    monkeypatch.setattr("core.test_case_rules.load_persistent_pages", lambda: {})
    bad = TestCaseList(story_summary="s", test_cases=[REVISED_ONLY, LISTING],
                       coverage=[_cov("AC1", REVISED_ONLY.title), _cov("AC2", REVISED_ONLY.title),
                                 _cov("AC3", LISTING.title)])
    good = TestCaseList(story_summary="s", test_cases=[REVISED_ONLY, LISTING, ABSENCE],
                        coverage=[_cov("AC1", ABSENCE.title), _cov("AC2", REVISED_ONLY.title),
                                  _cov("AC3", LISTING.title)])
    llm = _FakeLLM(bad, good)
    assert agent1_analyst._draft_test_cases(llm, "PROMPT", CRITERIA) is good
    assert "# Your previous answer was rejected" in llm.prompts[1] and "AC1 " in llm.prompts[1]


def test_agent1_writes_nothing_when_the_retry_still_misses_it(monkeypatch):
    from agents import agent1_analyst
    monkeypatch.setattr("core.test_case_rules.load_persistent_pages", lambda: {})
    bad = TestCaseList(story_summary="s", test_cases=[REVISED_ONLY],
                       coverage=[_cov("AC1", REVISED_ONLY.title)])
    with pytest.raises(ValueError, match="rejected twice; nothing was written"):
        agent1_analyst._draft_test_cases(_FakeLLM(bad, bad), "PROMPT", CRITERIA)


def test_impact_aware_rejects_a_revision_that_only_stopped_using_the_field():
    from agents.agent1_impact import validate_draft
    draft = ImpactAwareDraft(
        story_summary="s",
        revisions=[TestCaseRevision(key="LIB-7", revised=REVISED_ONLY, change_note="no renewals")],
        new_test_cases=[LISTING],
        coverage=[_cov("AC1", "LIB-7"), _cov("AC2", "LIB-7"), _cov("AC3", LISTING.title)])
    errors, _near = validate_draft(draft, {"LIB-7"}, set(), {}, {"LIB-7": "Borrow"}, CRITERIA)
    assert any(e.startswith("AC1 ") for e in errors)

    fixed = draft.model_copy(update={
        "new_test_cases": [LISTING, ABSENCE],
        "coverage": [_cov("AC1", ABSENCE.title), _cov("AC2", "LIB-7"), _cov("AC3", LISTING.title)]})
    errors, _near = validate_draft(fixed, {"LIB-7"}, set(), {}, {"LIB-7": "Borrow"}, CRITERIA)
    assert errors == []


def test_both_prompts_carry_the_criteria_and_the_obligation_table():
    from config.paths import PROMPTS_DIR
    for name in ("agent1_analyst.md", "agent1_impact_aware.md"):
        text = (PROMPTS_DIR / name).read_text(encoding="utf-8")
        assert "{criteria_block}" in text, name
        assert "Prove the OLD state is gone" in text, name
        assert "sets a limit or a validation rule" in text, name
