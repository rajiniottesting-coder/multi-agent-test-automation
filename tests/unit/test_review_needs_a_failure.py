"""A review stops a pull request only by naming how the code fails.

PR #148 (SCRUM-111): the review filed a `blocking` / `functional_bug` whose
own description walked the flow and ended "This flow is valid. No blocking
bug - downgrading." The severity was never changed, the gate went red, and
every test had passed. Blocking now needs positive evidence - a non-empty
`failure_scenario` - rather than the absence of a retraction phrase.
"""
from agents.agent3_reviewer import derive_verdict, format_review_as_markdown
from core.schemas import ReviewIssue, ReviewReport

ReviewIssue.__test__ = False

THE_REAL_ONE = (
    "In the repeat-add scenario, the first add step dismisses the dialog ... This flow is "
    "valid. No blocking bug - downgrading."
)


def _report(*issues, verdict="request_changes"):
    return ReviewReport(pr_number=148, overall_verdict=verdict, summary="s",
                        issues=list(issues), style_compliance=True,
                        type_hints_present=True, no_hardcoded_waits=True,
                        pom_compliant=True, coverage_complete=True)


def _issue(severity="blocking", issue_type="functional_bug", failure=None,
           description=THE_REAL_ONE):
    return ReviewIssue(severity=severity, file_path="features/x.feature",
                       issue_type=issue_type, description=description,
                       suggested_fix="f", failure_scenario=failure)


def test_the_pr_148_finding_no_longer_blocks_and_is_still_shown():
    out = derive_verdict(_report(_issue(), _issue("minor", "best_practice")))
    assert out.overall_verdict == "comment"
    assert [i.severity for i in out.issues] == ["major", "minor"]
    assert THE_REAL_ONE in out.issues[0].description


def test_a_blocking_finding_with_a_failure_still_blocks():
    out = derive_verdict(_report(_issue(failure="Scenario A: step B raises KeyError"),
                                 verdict="comment"))
    assert out.overall_verdict == "request_changes"
    assert out.issues[0].severity == "blocking"


def test_a_major_functional_bug_needs_a_failure_too():
    assert derive_verdict(_report(_issue("major"), verdict="comment")).overall_verdict == "comment"
    assert derive_verdict(_report(_issue("major", failure="X fails at line 3"),
                                  verdict="comment")).overall_verdict == "request_changes"


def test_whitespace_is_not_a_failure():
    assert derive_verdict(_report(_issue(failure="   "))).overall_verdict == "comment"


def test_security_blocks_without_one():
    out = derive_verdict(_report(_issue("minor", "security"), verdict="approve"))
    assert out.overall_verdict == "request_changes"


def test_the_failure_is_shown_in_the_comment():
    md = format_review_as_markdown(_report(_issue(failure="Scenario A: step B raises KeyError")))
    assert "**Fails when:** Scenario A: step B raises KeyError" in md
