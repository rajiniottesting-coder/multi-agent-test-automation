"""A predicted test failure is checked against the run of that test.

PR #148 (SCRUM-111), second review: a major/functional_bug predicted "if the
site renders two separate rows ... the assertion fails", with the fix "No code
change needed if behaviour is confirmed". Agent 4 had already run all four
scenarios on that commit, green. The review now waits for the runner when a
predicted failure is the only thing blocking, and a green run refutes it.
"""
from agents.agent3_reviewer import (
    _needs_runner_evidence,
    align_labels_with_verdict,
    derive_verdict,
    runner_result_for_head,
)
from agents.agent3_reviewer import apply_runner_evidence as _apply


def apply_runner_evidence(report, result):
    """Evidence, then the verdict re-derived from the labels - as the chain does."""
    return align_labels_with_verdict(_apply(report, result))
from core.schemas import ReviewIssue, ReviewReport

ReviewIssue.__test__ = False

FAILS = ("Scenario 'Adding the same product twice': if the site renders two "
         "separate rows, quantity_for reads 1 and the assertion fails.")


def _issue(severity="major", issue_type="functional_bug", outcome=None, failure=FAILS):
    return ReviewIssue(severity=severity, file_path="tests/step_defs/test_x.py",
                       issue_type=issue_type, description="d", suggested_fix="f",
                       failure_scenario=failure, test_outcome=outcome)


def _report(*issues):
    return derive_verdict(ReviewReport(
        pr_number=148, overall_verdict="comment", summary="s", issues=list(issues),
        style_compliance=True, type_hints_present=True, no_hardcoded_waits=True,
        pom_compliant=True, coverage_complete=True))


def test_the_pr_148_prediction_is_refuted_by_a_green_run_and_kept_visible():
    report = _report(_issue(), _issue("minor", "best_practice", failure=None))
    assert report.overall_verdict == "request_changes"
    assert _needs_runner_evidence(report)
    out = apply_runner_evidence(report, "success")
    assert out.overall_verdict == "comment"
    assert len(out.issues) == 2 and "Refuted by the runner" in out.issues[0].description


def test_a_red_or_missing_run_keeps_the_block():
    report = _report(_issue())
    for result in ("failure", "cancelled", None):
        assert apply_runner_evidence(report, result).overall_verdict == "request_changes"


def test_passing_wrongly_is_not_refuted_by_a_pass():
    report = _report(_issue(outcome="passes_wrongly"))
    assert not _needs_runner_evidence(report)
    assert apply_runner_evidence(report, "success").overall_verdict == "request_changes"


def test_a_refuted_prediction_stops_blocking_beside_a_real_blocker():
    """Judged one by one: the style finding still blocks, the refuted prediction
    no longer sits under Blocking beside it."""
    report = _report(_issue(), _issue("blocking", "style", failure="Line 3 raises."))
    assert _needs_runner_evidence(report)
    out = apply_runner_evidence(report, "success")
    assert out.overall_verdict == "request_changes"
    assert [(i.issue_type, i.severity) for i in out.issues] == [
        ("best_practice", "info"), ("style", "blocking")]


def test_security_never_waits():
    assert not _needs_runner_evidence(_report(_issue("minor", "security", failure=None)))


class _Host:
    def __init__(self, polls):
        self.polls = list(polls)

    def list_open_prs(self, branch_prefix=""):
        return [{"number": 148, "head_sha": "abc"}, {"number": 1, "head_sha": "zzz"}]

    def get_workflow_runs(self, workflow_file, branch, limit=20):
        return self.polls.pop(0) if len(self.polls) > 1 else self.polls[0]


def _clock():
    t = {"now": 0}

    def clock():
        return t["now"]

    def sleep(seconds):
        t["now"] += seconds
    return clock, sleep


def test_the_runner_is_read_for_this_commit_only_and_waited_for():
    clock, sleep = _clock()
    host = _Host([
        [{"status": "completed", "conclusion": "failure", "head_sha": "old"}],
        [{"status": "in_progress", "conclusion": None, "head_sha": "abc"}],
        [{"status": "completed", "conclusion": "success", "head_sha": "abc"}],
    ])
    assert runner_result_for_head(host, 148, "auto/X-1-y", wait_seconds=100,
                                  poll_seconds=10, sleep=sleep, clock=clock) == "success"


def test_no_result_by_the_deadline_is_none():
    clock, sleep = _clock()
    host = _Host([[{"status": "in_progress", "conclusion": None, "head_sha": "abc"}]])
    assert runner_result_for_head(host, 148, "b", wait_seconds=30, poll_seconds=10,
                                  sleep=sleep, clock=clock) is None


def test_a_closed_pr_has_no_evidence():
    assert runner_result_for_head(_Host([[]]), 999, "b", wait_seconds=0) is None
