"""A review's verdict must follow from what the review found.

WHAT HAPPENED
    Agent 3 reported an issue at severity `major` and type `functional_bug` -
    a type the schema defines as "test will fail" - and returned the verdict
    `comment`, which renders as "Advisory comments". Both statements came from
    the same call, in the same object, and they contradicted each other.

    The finding was right. The next run failed on the exact line the review
    named, for the exact reason it gave, and the fix it suggested was correct.
    Nothing acted on any of that, because the verdict is what the pipeline
    reads and the verdict said advisory.

    Two fields, filled independently, free to disagree - the same shape as
    every other expensive failure here: the framework holding two views at
    once and acting on the wrong one.

WHY DERIVE RATHER THAN PROMPT
    A prompt asking for consistency between two fields is followed until it
    is not, and nothing notices. Severity is a judgement the model is well
    placed to make; what a severity MEANS for a pull request is arithmetic.
    So the model still reports what it found, and the verdict is computed.
"""
import pytest

from agents.agent3_reviewer import derive_verdict
from core.schemas import ReviewIssue, ReviewReport


def _report(verdict: str, *issues: ReviewIssue) -> ReviewReport:
    return ReviewReport(
        pr_number=1,
        overall_verdict=verdict,
        summary="s",
        issues=list(issues),
        style_compliance=True,
        type_hints_present=True,
        no_hardcoded_waits=True,
        pom_compliant=True,
        coverage_complete=True,
    )


def _issue(severity: str, issue_type: str) -> ReviewIssue:
    return ReviewIssue(
        severity=severity,
        file_path="some/file.py",
        line_number=1,
        issue_type=issue_type,
        description="d",
        suggested_fix="f",
    )


# ─────────────────────────────────────────────────────────────────────────
# The exact shape that shipped a broken test
# ─────────────────────────────────────────────────────────────────────────

def test_a_functional_bug_is_never_advisory():
    """major + functional_bug + 'comment' is what actually happened."""
    out = derive_verdict(_report("comment", _issue("major", "functional_bug")))
    assert out.overall_verdict == "request_changes", (
        "the schema defines functional_bug as 'test will fail'. A review "
        "cannot say that and call itself advisory."
    )


def test_a_blocking_severity_is_never_advisory():
    out = derive_verdict(_report("comment", _issue("blocking", "style")))
    assert out.overall_verdict == "request_changes"


def test_a_security_issue_is_never_advisory():
    out = derive_verdict(_report("approve", _issue("minor", "security")))
    assert out.overall_verdict == "request_changes"


# ─────────────────────────────────────────────────────────────────────────
# Break the thing the guard guards
#
# A rule that raised every verdict would be no rule at all - the gate would
# be red on every pull request and would be turned off within a week.
# ─────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("issue_type", ["style", "best_practice", "missing_coverage"])
@pytest.mark.parametrize("severity", ["major", "minor", "info"])
def test_advisory_findings_stay_advisory(severity, issue_type):
    out = derive_verdict(_report("comment", _issue(severity, issue_type)))
    assert out.overall_verdict == "comment", (
        f"{severity}/{issue_type} does not assert the code is broken - "
        f"raising it would make the gate meaningless"
    )


def test_a_clean_review_still_approves():
    out = derive_verdict(_report("approve"))
    assert out.overall_verdict == "approve"


def test_the_rule_only_ever_raises():
    """A model that asked for changes keeps them, whatever the severities."""
    out = derive_verdict(_report("request_changes", _issue("info", "style")))
    assert out.overall_verdict == "request_changes"


def test_the_issues_themselves_are_untouched():
    """The verdict is recomputed; the findings are the model's and stay so."""
    issues = (_issue("major", "functional_bug"), _issue("minor", "style"))
    out = derive_verdict(_report("comment", *issues))
    assert [(i.severity, i.issue_type) for i in out.issues] == \
        [(i.severity, i.issue_type) for i in issues]


# ─────────────────────────────────────────────────────────────────────────
# The verdict has to reach something that acts on it
#
# Deriving it changes nothing if the job still exits 0 whatever it says.
# That was the second half of the same failure: the review was posted as a
# comment and the workflow reported success, so the runner went ahead and
# proved the review right.
# ─────────────────────────────────────────────────────────────────────────

def test_requesting_changes_fails_the_job():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[2] / "agents"
              / "agent3_reviewer.py").read_text(encoding="utf-8")
    body = " ".join(source.split())

    assert 'result.get("verdict") == "request_changes"' in body, (
        "nothing in Agent 3 compares the verdict against request_changes"
    )
    marker = body.index('result.get("verdict") == "request_changes"')
    assert "sys.exit(1)" in body[marker:marker + 400], (
        "a requested-changes verdict must fail the job. Posting a comment and "
        "exiting 0 is how a correct finding got walked past."
    )