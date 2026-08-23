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
def test_advisory_findings_stay_advisory(issue_type):
    """One case per non-blocking TYPE, at the highest non-blocking severity.

    A grid over severity as well would be nine node IDs asserting one thing:
    that `major` is not by itself blocking. `major` is the only severity that
    could plausibly be treated as blocking, so it is the only one worth
    spending a case on - `minor` and `info` follow from it, and testing them
    separately measures the parametrize decorator, not the rule.
    """
    out = derive_verdict(_report("comment", _issue("major", issue_type)))
    assert out.overall_verdict == "comment", (
        f"major/{issue_type} does not assert the code is broken - raising it "
        f"would make the gate red on every pull request, and a gate that is "
        f"always red gets turned off"
    )


def test_a_clean_review_still_approves():
    out = derive_verdict(_report("approve"))
    assert out.overall_verdict == "approve"


def test_an_advisory_finding_alone_does_not_keep_a_blocking_verdict():
    """This test used to assert the opposite - that the rule only ever RAISED,
    and a model asking for changes kept them whatever the severities.

    That reasoning held until a review filed two `minor` / `best_practice`
    wording notes, called the code acceptable in its own summary, and
    returned request_changes. The pull request went red on readability while
    the runner was green.

    Blocking is a budget. A gate that spends it on advisory findings is a gate
    people learn to override, and the severity field exists precisely so the
    review can say which findings are worth stopping for.
    """
    out = derive_verdict(_report("request_changes", _issue("info", "style")))
    assert out.overall_verdict == "comment"


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


# =========================================================================
# A finding that withdraws itself does not stop a pull request
#
# THE SAME BUG, THREE TIMES, EACH TIME ONE NOTCH HIGHER
#   v1 blocked on issue TYPE alone. A `minor` / `functional_bug` whose fix
#   read "No change required for current scenarios" turned the PR red.
#   v2 required severity >= major. A `major` / `functional_bug` whose
#   description ended "the pattern is acceptable given actual scenario data"
#   and whose fix opened "No change required for current scenarios" turned
#   the PR red. Same sentence, same outcome, one severity up.
#
#   The threshold cannot go higher without discarding functional_bug
#   detection entirely, so the threshold was never the answer. The finding
#   contradicts ITSELF - the same shape as the verdict/severity split this
#   module already resolves - and is read the same way: the more specific
#   statement wins.
# =========================================================================


def _waived(severity: str, issue_type: str, fix: str) -> ReviewIssue:
    return ReviewIssue(
        severity=severity,
        file_path="some/file.py",
        line_number=1,
        issue_type=issue_type,
        description="d",
        suggested_fix=fix,
    )


_THE_REAL_ONE = (
    "No change required for current scenarios since search terms are always "
    "non-empty. If empty search is ever added, switch to parsers.re with "
    "r'I search for \"(?P<term>[^\"]*)\"'."
)


def test_the_finding_that_shipped_does_not_block():
    """major / functional_bug whose own fix opens 'No change required'."""
    out = derive_verdict(_report(
        "comment", _waived("major", "functional_bug", _THE_REAL_ONE)))
    assert out.overall_verdict == "comment", (
        "the review asked for nothing and the pull request went red anyway"
    )


def test_a_trailing_hypothetical_does_not_revive_it():
    """'If X is ever added, switch to Y' is advice for a change not requested."""
    out = derive_verdict(_report("comment", _waived(
        "major", "functional_bug",
        "No action needed. If the schema grows a field, revisit this.")))
    assert out.overall_verdict == "comment"


# ─────────────────────────────────────────────────────────────────────────
# Break the thing the guard guards
#
# A waiver rule that is too eager silently drops real findings, which is
# strictly worse than the red gate it replaced: the gate was noisy, this
# would be quiet.
# ─────────────────────────────────────────────────────────────────────────

def test_a_real_functional_bug_still_blocks():
    out = derive_verdict(_report("comment", _waived(
        "major", "functional_bug",
        "Rewrite the assertion to use wait_for_row() instead of reading the list.")))
    assert out.overall_verdict == "request_changes"


@pytest.mark.parametrize("fix", [
    "No change required to the selector, but the assertion must be rewritten.",
    "No change is needed unless the schema changes.",
    "No change required, however the fixture should still be renamed.",
])
def test_a_waiver_taken_back_in_the_same_sentence_still_blocks(fix):
    """An adversative means something IS being asked for."""
    out = derive_verdict(_report(
        "comment", _waived("major", "functional_bug", fix)))
    assert out.overall_verdict == "request_changes", (
        f"{fix!r} asks for a change despite opening with a waiver"
    )


def test_a_security_finding_cannot_waive_itself():
    """A security finding that shrugs is still worth one look."""
    out = derive_verdict(_report("approve", _waived(
        "minor", "security", "No change required; the token is a test fixture.")))
    assert out.overall_verdict == "request_changes"


def test_an_explicit_blocking_severity_cannot_be_waived():
    """`blocking` is a deliberate call, not something a phrase overturns."""
    out = derive_verdict(_report(
        "comment", _waived("blocking", "style", "No change needed.")))
    assert out.overall_verdict == "request_changes"


@pytest.mark.parametrize("fix", ["", "Nothing to do here.", "Looks fine."])
def test_only_the_explicit_phrase_waives(fix):
    """Near-misses must NOT waive - the rule is deliberately narrow."""
    out = derive_verdict(_report(
        "comment", _waived("major", "functional_bug", fix)))
    assert out.overall_verdict == "request_changes"


# =========================================================================
# THE VERDICT DERIVES IN BOTH DIRECTIONS
#
# derive_verdict only ever RAISED, on the reasoning that a model wanting to
# block should be trusted to. That left the severity field meaningless in one
# direction.
#
# A review filed two `minor` / `best_practice` findings - both wording
# suggestions, its own summary calling the code "acceptable" - and returned
# request_changes. The pull request went red on readability notes while
# Agent 4 was green.
#
# A gate that blocks on advisory findings is a gate people learn to override,
# and then it is not a gate. If a review wants to stop a pull request it has
# to file something that says so.
# =========================================================================

def test_minor_findings_alone_do_not_block(project=None):
    """The run that prompted this."""
    out = derive_verdict(_report("request_changes",
                                 _issue("minor", "best_practice"),
                                 _issue("minor", "best_practice")))
    assert out.overall_verdict == "comment", (
        "two wording suggestions blocked a pull request that the runner had "
        "already passed"
    )


def test_a_blocking_finding_still_blocks_when_the_model_says_block():
    """Break the thing the guard guards, part one. Lowering must not lower
    everything - a review with a real finding keeps its verdict."""
    out = derive_verdict(_report("request_changes",
                                 _issue("major", "functional_bug")))
    assert out.overall_verdict == "request_changes"


def test_a_blocking_finding_still_raises_an_advisory_verdict():
    """Break the thing the guard guards, part two. The raising half must
    survive the lowering half - they are the same rule read two ways."""
    out = derive_verdict(_report("comment", _issue("major", "functional_bug")))
    assert out.overall_verdict == "request_changes"

    out = derive_verdict(_report("approve", _issue("minor", "security")))
    assert out.overall_verdict == "request_changes"


def test_a_review_with_no_findings_cannot_block():
    """A verdict with nothing behind it is an opinion, not a gate."""
    out = derive_verdict(_report("request_changes"))
    assert out.overall_verdict == "comment"


def test_an_approve_with_no_findings_is_left_alone():
    """Lowering applies to request_changes only. Nothing should turn an
    approve into a comment."""
    out = derive_verdict(_report("approve"))
    assert out.overall_verdict == "approve"