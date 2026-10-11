"""A review blocks a pull request only for what the pull request changed.

A PR that changed one line of a test file was blocked for a different,
pre-existing line of that file - and the same code had passed review on the
previous run. Findings on unchanged lines are shown as pre-existing notes.
Generic names only; no network, no model.
"""
import pytest

from agents.agent3_reviewer import (
    changed_line_map,
    lower_findings_on_unchanged_lines,
    postprocess_review,
)
from core.schemas import ReviewIssue, ReviewReport

ReviewIssue.__test__ = False

PATCH = "@@ -31,7 +31,7 @@ def test_one():\n     a\n-    old\n+    new\n     b\n"
CHANGED = changed_line_map([
    {"filename": "tests/unit/test_widget.py", "status": "modified", "patch": PATCH},
    {"filename": "pages/widget_page.py", "status": "added", "patch": "@@ -0,0 +1,9 @@"},
    {"filename": "big.bin", "status": "modified", "patch": None},
])


def _issue(path="tests/unit/test_widget.py", line=54, sev="blocking", typ="functional_bug"):
    return ReviewIssue(severity=sev, file_path=path, line_number=line, issue_type=typ,
                       description="d", suggested_fix="f",
                       failure_scenario="Test X: line passes vacuously.",
                       test_outcome="passes_wrongly")


def _report(*issues):
    return ReviewReport(pr_number=1, overall_verdict="request_changes", summary="s",
                        issues=list(issues), style_compliance=True, type_hints_present=True,
                        no_hardcoded_waits=True, pom_compliant=True, coverage_complete=True)


def test_the_map_covers_hunks_with_a_margin_added_files_whole_and_skips_unreadable():
    assert {31, 37, 28, 39} <= CHANGED["tests/unit/test_widget.py"]
    assert 54 not in CHANGED["tests/unit/test_widget.py"]
    assert CHANGED["pages/widget_page.py"] == "all"
    assert "big.bin" not in CHANGED


def test_the_real_case_a_pre_existing_line_no_longer_blocks():
    final, _ = postprocess_review(_report(_issue()), changed_lines=CHANGED)
    assert final.overall_verdict != "request_changes"
    assert final.issues[0].severity == "info"
    assert final.issues[0].description.startswith("Pre-existing")


@pytest.mark.parametrize("issue", [
    _issue(line=33),                                   # on a changed line
    _issue(path="pages/widget_page.py", line=500),     # a file this PR added
    _issue(line=None),                                 # no location to judge
    _issue(path="big.bin", line=9),                    # no patch to read
    _issue(line=54, typ="security"),                   # security is never lowered
])
def test_blocking_stands_when_the_finding_is_on_the_change_or_cannot_be_placed(issue):
    final, _ = postprocess_review(_report(issue), changed_lines=CHANGED)
    assert final.overall_verdict == "request_changes"


def test_without_a_map_nothing_changes():
    report = _report(_issue())
    assert lower_findings_on_unchanged_lines(report, None) is report


@pytest.mark.parametrize("sev", ["blocking", "major", "minor", "info"])
@pytest.mark.parametrize("typ", ["style", "functional_bug", "missing_coverage",
                                 "security", "best_practice"])
@pytest.mark.parametrize("outcome", [None, "fails", "passes_wrongly"])
def test_invariant_only_security_blocks_from_an_unchanged_line(sev, typ, outcome):
    issue = ReviewIssue(severity=sev, file_path="x.py", line_number=100, issue_type=typ,
                        description="d", suggested_fix="Rename it.",
                        failure_scenario="Step A raises.", test_outcome=outcome)
    final, _ = postprocess_review(_report(issue), get_runner_result=lambda: "failure",
                                  changed_lines={"x.py": set(range(1, 10))})
    assert (final.overall_verdict == "request_changes") == (typ == "security")
