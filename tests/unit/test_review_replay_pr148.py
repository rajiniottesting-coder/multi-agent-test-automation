"""Replay of all five real reviews of PR #148 through the whole post-processing chain.

Each review was fixed in isolation and the next one failed differently. This
runs every one of them, as the model filed it, through everything between the
model's answer and the posted comment - so a change that fixes one and
breaks another fails here, not on the next pull request.

What a human must see for all five (Agent 4 ran green on that commit):
  - the verdict does not block
  - no finding is still labelled a functional bug
  - the summary does not announce a functional bug the findings no longer hold
"""
import pytest

from agents.agent3_reviewer import format_review_as_markdown, postprocess_review
from core.schemas import ReviewIssue, ReviewReport

ReviewIssue.__test__ = False

_DEAD_CODE = {"severity": "minor", "file_path": "pages/product_detail_page.py",
              "issue_type": "best_practice", "description": "set_quantity() is unused.",
              "suggested_fix": "Remove it or use it."}

# 1st review: blocking, the description retracts itself, no failure named.
RUN_1 = ReviewReport(
    pr_number=148, overall_verdict="request_changes",
    summary="SCRUM-215 has a blocking functional bug in the repeat add.",
    issues=[ReviewIssue(severity="blocking", file_path="features/cart_management.feature",
                        issue_type="functional_bug",
                        description="The second add re-opens the modal. This flow is valid. "
                                    "No blocking bug - downgrading.",
                        suggested_fix="None."),
            ReviewIssue(**_DEAD_CODE)],
    style_compliance=True, type_hints_present=True, no_hardcoded_waits=True,
    pom_compliant=True, coverage_complete=True)

# 2nd review: major, a CONDITIONAL failure on app behaviour, fix asks to confirm.
RUN_2 = RUN_1.model_copy(update={
    "summary": "There is a genuine functional bug in SCRUM-215.",
    "issues": [ReviewIssue(severity="major", file_path="tests/step_defs/test_cart_management.py",
                           issue_type="functional_bug",
                           description="Quantity 2 depends on the app merging repeat adds - "
                                       "acceptable, flag only for verification.",
                           suggested_fix="Confirm the app increments quantity on a repeated "
                                         "add. No code change needed if behaviour is confirmed.",
                           failure_scenario="If the site renders two separate rows, "
                                            "quantity_for reads 1 and the assertion fails.",
                           test_outcome="fails"),
               ReviewIssue(**_DEAD_CODE)]})

# 3rd review: major, no failure named, own fix says nothing is required.
RUN_3 = RUN_1.model_copy(update={
    "overall_verdict": "comment",
    "summary": "SCRUM-215 has a functional bug: adding the same product twice does not "
               "increase quantity to 2.",
    "issues": [ReviewIssue(severity="major", file_path="features/cart_management.feature",
                           issue_type="functional_bug",
                           description="Relies on app-side merge; the assertion is legitimately "
                                       "the test's job.",
                           suggested_fix="No change required if the app merges duplicate "
                                         "additions into quantity 2. Leaving as advisory."),
               ReviewIssue(**_DEAD_CODE)]})


# 4th review: the re-run that used the stale reviewer from the story branch.
RUN_4 = RUN_1.model_copy(update={
    "summary": "There is also a functional bug in the SCRUM-215 step wiring.",
    "issues": [ReviewIssue(severity="major", file_path="features/cart_management.feature",
                           issue_type="functional_bug",
                           description="... so this is acceptable; however the quantity assertion "
                                       "of 2 depends on the app incrementing.",
                           suggested_fix="Confirm that adding the same product twice increments "
                                         "quantity to 2; if the app produces two rows, the "
                                         "assertion will fail."),
               ReviewIssue(**_DEAD_CODE)]})

# 5th review: the first with the current reviewer - names a failure AND waives it.
RUN_5 = RUN_1.model_copy(update={
    "overall_verdict": "comment",
    "summary": "SCRUM-215 relies on quantity aggregation.",
    "issues": [ReviewIssue(severity="major", file_path="features/cart_management.feature",
                           issue_type="functional_bug",
                           description="Adds the product twice from the same detail page.",
                           suggested_fix="No code change required if the site aggregates two "
                                         "single adds into quantity 2. Leaving as advisory.",
                           failure_scenario="If the app behaves as the test case states this "
                                            "passes. This is the test doing its job - downgrading.",
                           test_outcome="fails"),
               ReviewIssue(**_DEAD_CODE)]})


@pytest.mark.parametrize("filed", [RUN_1, RUN_2, RUN_3, RUN_4, RUN_5],
                         ids=["run1", "run2", "run3", "run4", "run5"])
def test_every_real_review_of_pr_148_comes_out_consistent(filed):
    final, withdrawn = postprocess_review(filed, get_runner_result=lambda: "success")
    md = format_review_as_markdown(final, withdrawn_count=len(withdrawn))

    assert final.overall_verdict != "request_changes"
    assert not any(i.issue_type == "functional_bug" for i in final.issues)
    assert "functional bug" not in final.summary.lower()
    assert "[functional_bug]" not in md
    assert "Fails when" not in md
    assert "Major" not in md, "nothing the reviewer itself withdrew or the run refuted ranks as major"
    assert any(i.description == _DEAD_CODE["description"] for i in final.issues), \
        "a real, unrelated finding survives untouched"


def test_a_red_run_still_blocks_the_conditional_prediction():
    final, _ = postprocess_review(RUN_2, get_runner_result=lambda: "failure")
    assert final.overall_verdict == "request_changes"


def test_an_untouched_review_keeps_the_model_summary():
    clean = RUN_1.model_copy(update={"overall_verdict": "comment", "summary": "Looks good.",
                                     "issues": [ReviewIssue(**_DEAD_CODE)]})
    final, withdrawn = postprocess_review(clean)
    assert final.summary == "Looks good." and not withdrawn


def test_the_withdrawn_finding_is_footnoted_not_listed():
    final, withdrawn = postprocess_review(RUN_3, get_runner_result=lambda: "success")
    assert len(withdrawn) == 1
    md = format_review_as_markdown(final, withdrawn_count=len(withdrawn))
    assert "1 further finding(s) were withdrawn" in md
    assert "Leaving as advisory" not in md
