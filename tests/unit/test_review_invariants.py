"""Invariants of the review chain, checked over every combination of finding.

Five rounds of fixes on PR #148 each closed the case in front of them and the
next model answer arrived in a shape nobody had listed. A model's wording
cannot be enumerated; the properties of the COMMENT a human reads can. Every
combination of severity, type, failure scenario, predicted outcome, waiver
and runner result goes through postprocess_review, and the result must hold:

  I1  a security finding always blocks
  I2  the verdict blocks exactly when a finding is shown under Blocking
  I3  after a green run, nothing that only predicts a failing test still blocks
  I4  a finding labelled functional_bug always names its failure
  I5  "Refuted by the runner" appears only after a green run
  I6  when findings changed, the model's summary is not shown
  I7  no finding is listed whose own fix asks for nothing (security aside)
  I8  a finding the runner refuted never shows a failure scenario
"""
import itertools

import pytest

from agents.agent3_reviewer import (
    _REFUTED_NOTE,
    _refutable_by_a_green_run,
    _waives_itself,
    postprocess_review,
)
from core.schemas import ReviewIssue, ReviewReport

ReviewIssue.__test__ = False

SEVERITIES = ["blocking", "major", "minor", "info"]
TYPES = ["style", "functional_bug", "missing_coverage", "security", "best_practice"]
FAILURES = [None, "Scenario A, step B: line 3 raises KeyError."]
OUTCOMES = [None, "fails", "passes_wrongly"]
FIXES = ["Rename the method.", "No change required if the app merges rows."]
RUNNER = ["success", "failure", None]
MODEL_SUMMARY = "MODEL SUMMARY - names a functional bug."


def _issue(sev, typ, failure, outcome, fix):
    return ReviewIssue(severity=sev, file_path="x.py", issue_type=typ, description="d",
                       suggested_fix=fix, failure_scenario=failure, test_outcome=outcome)


def _report(*issues, verdict="request_changes"):
    return ReviewReport(pr_number=1, overall_verdict=verdict, summary=MODEL_SUMMARY,
                        issues=list(issues), style_compliance=True, type_hints_present=True,
                        no_hardcoded_waits=True, pom_compliant=True, coverage_complete=True)


CASES = list(itertools.product(SEVERITIES, TYPES, FAILURES, OUTCOMES, FIXES, RUNNER))


@pytest.mark.parametrize("sev,typ,failure,outcome,fix,runner", CASES)
def test_one_finding(sev, typ, failure, outcome, fix, runner):
    filed = _report(_issue(sev, typ, failure, outcome, fix))
    final, withdrawn = postprocess_review(filed, get_runner_result=lambda: runner)
    _check(filed, final, withdrawn, runner)


@pytest.mark.parametrize("runner", RUNNER)
@pytest.mark.parametrize("pair", list(itertools.combinations(
    [("blocking", "style", FAILURES[1], None, FIXES[0]),
     ("major", "functional_bug", FAILURES[1], "fails", FIXES[0]),
     ("major", "functional_bug", None, None, FIXES[1]),
     ("blocking", "best_practice", FAILURES[1], "fails", FIXES[0]),
     ("minor", "security", None, None, FIXES[1]),
     ("major", "functional_bug", FAILURES[1], "passes_wrongly", FIXES[0])], 2)))
def test_two_findings(pair, runner):
    filed = _report(*(_issue(*spec) for spec in pair))
    final, withdrawn = postprocess_review(filed, get_runner_result=lambda: runner)
    _check(filed, final, withdrawn, runner)


def _check(filed, final, withdrawn, runner):
    shown_blocking = [i for i in final.issues if i.severity == "blocking"]
    # I1
    if any(i.issue_type == "security" for i in filed.issues):
        assert final.overall_verdict == "request_changes"
    # I2
    assert (final.overall_verdict == "request_changes") == bool(shown_blocking)
    # I3
    if runner == "success":
        assert not [i for i in shown_blocking if _refutable_by_a_green_run(i)]
    # I4
    for i in final.issues:
        if i.issue_type == "functional_bug":
            assert (i.failure_scenario or "").strip()
    # I5
    if runner != "success":
        assert not any(_REFUTED_NOTE in i.description for i in final.issues)
    # I6
    changed = withdrawn or [(i.severity, i.issue_type, i.description) for i in filed.issues] != \
        [(i.severity, i.issue_type, i.description) for i in final.issues]
    if changed:
        assert final.summary != MODEL_SUMMARY
    # I7
    for i in final.issues:
        if i.issue_type != "security":
            assert not _waives_itself(i)
    # I8
    for i in final.issues:
        if _REFUTED_NOTE in i.description:
            assert not i.failure_scenario


def test_the_matrix_is_the_size_it_claims():
    assert len(CASES) == 4 * 5 * 2 * 3 * 2 * 3
