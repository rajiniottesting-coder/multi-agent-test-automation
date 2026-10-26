"""A predicted failure is judged on ITS scenario's result, not the whole run's.

PR #211 (SCRUM-206): the reviewer blocked on "the add-from-card step will hit
two controls in one card". That scenario passed on the commit; the run was red
only because ANOTHER test hit an HTTP 503 from the application - and a change
story's PR is red by design until the change is deployed. A whole-run rule kept
the wrong prediction blocking. And the helper the finding was about documents
that it handles the case, but the reviewer never saw its docstring.

Written against a different application (a library) on purpose.
"""
from __future__ import annotations

import io
import zipfile

import pytest

from agents.agent3_reviewer import (
    RunnerEvidence, _needs_runner_evidence, _predicted_scenario, align_labels_with_verdict,
    base_page_helpers_called, derive_verdict, parse_junit_scenarios, runner_evidence_for_head,
    scenario_key,
)
from agents.agent3_reviewer import apply_runner_evidence as _apply
from core.schemas import ReviewIssue, ReviewReport

ReviewIssue.__test__ = False


def apply(report, evidence):
    return align_labels_with_verdict(_apply(report, evidence))


def _issue(scenario=None, failure="the step raises", outcome="fails", issue_type="functional_bug",
           severity="blocking"):
    return ReviewIssue(severity=severity, file_path="pages/catalogue_page.py",
                       issue_type=issue_type, description="d", suggested_fix="f",
                       failure_scenario=failure, test_outcome=outcome, scenario=scenario)


def _report(*issues):
    return derive_verdict(ReviewReport(
        pr_number=7, overall_verdict="comment", summary="s", issues=list(issues),
        style_compliance=True, type_hints_present=True, no_hardcoded_waits=True,
        pom_compliant=True, coverage_complete=True))


def _junit(**cases):
    """cases: {test name: outcome}."""
    body = []
    for name, outcome in cases.items():
        inner = {"failed": "<failure message='x'/>", "error": "<error message='x'/>",
                 "skipped": "<skipped/>", "passed": ""}[outcome]
        body.append(f'<testcase classname="tests.step_defs.test_loans" name="{name}">{inner}</testcase>')
    return ("<testsuites><testsuite name='pytest'>" + "".join(body)
            + "</testsuite></testsuites>").encode()


RED_ELSEWHERE = _junit(test_borrow_a_book_from_its_catalogue_card="passed",
                       test_return_a_book_from_the_loan_page="failed")     # e.g. an outage


# ─────────────────────────────────────────────────────────────
# Reading the report
# ─────────────────────────────────────────────────────────────
def test_a_scenario_title_and_its_generated_test_share_a_key():
    assert scenario_key("Searching for a non-existent title shows no books") == \
        scenario_key("test_searching_for_a_nonexistent_title_shows_no_books")
    assert scenario_key("test_renew_a_loan[Dune-2]") == scenario_key("Renew a loan")


def test_the_junit_report_gives_each_scenario_its_outcomes():
    xml = _junit(test_a="passed", test_b="failed", test_c="error", test_d="skipped")
    assert parse_junit_scenarios(xml) == {"a": ["passed"], "b": ["failed"], "c": ["error"],
                                          "d": ["skipped"]}
    assert parse_junit_scenarios(b"<not xml") is None
    assert parse_junit_scenarios(None) is None


def test_the_scenario_comes_from_the_field_or_the_failure_text():
    assert _predicted_scenario(_issue("Scenario: Borrow a book")) == "Borrow a book"
    assert _predicted_scenario(_issue(failure="Scenario 'Borrow a book from its catalogue "
                                              "card': at the 'When I borrow' step it raises")) \
        == "Borrow a book from its catalogue card"
    assert _predicted_scenario(_issue(failure="the click raises")) is None


# ─────────────────────────────────────────────────────────────
# The rule
# ─────────────────────────────────────────────────────────────
def test_the_pr_211_shape_a_passing_scenario_refutes_its_prediction_in_a_red_run():
    report = _report(_issue(failure="Scenario 'Borrow a book from its catalogue card': at the "
                                    "'When I borrow it from its card' step the click matches two "
                                    "controls and raises a strict-mode violation."))
    assert report.overall_verdict == "request_changes" and _needs_runner_evidence(report)
    out = apply(report, RunnerEvidence("failure", parse_junit_scenarios(RED_ELSEWHERE)))
    assert out.overall_verdict != "request_changes"
    assert "scenario 'Borrow a book from its catalogue card' was executed on this commit " \
           "and passed" in out.issues[0].description


@pytest.mark.parametrize("scenario, why", [
    ("Return a book from the loan page", "its own scenario failed"),
    ("Reserve a book", "not in the report"),
    (None, "names no scenario"),
])
def test_otherwise_a_red_run_keeps_the_block(scenario, why):
    report = _report(_issue(scenario))
    out = apply(report, RunnerEvidence("failure", parse_junit_scenarios(RED_ELSEWHERE)))
    assert out.overall_verdict == "request_changes", why


def test_an_unreadable_report_falls_back_to_the_whole_run():
    report = _report(_issue("Borrow a book from its catalogue card"))
    assert apply(report, RunnerEvidence("failure", None)).overall_verdict == "request_changes"
    assert apply(report, RunnerEvidence("success", None)).overall_verdict != "request_changes"
    assert apply(report, "success").overall_verdict != "request_changes"     # old call shape


def test_an_outline_is_refuted_only_when_every_example_passed():
    xml = _junit(**{"test_renew_a_loan[Dune]": "passed", "test_renew_a_loan[Emma]": "failed"})
    report = _report(_issue("Renew a loan"))
    assert apply(report, RunnerEvidence("failure", parse_junit_scenarios(xml))) \
        .overall_verdict == "request_changes"


def test_passing_wrongly_and_security_are_never_refuted_by_a_pass():
    passed = RunnerEvidence("failure", parse_junit_scenarios(RED_ELSEWHERE))
    for issue in (_issue("Borrow a book from its catalogue card", outcome="passes_wrongly"),
                  _issue("Borrow a book from its catalogue card", issue_type="security")):
        assert apply(_report(issue), passed).overall_verdict == "request_changes"


def test_each_prediction_is_judged_on_its_own_scenario():
    report = _report(_issue("Borrow a book from its catalogue card"),
                     _issue("Return a book from the loan page"))
    out = apply(report, RunnerEvidence("failure", parse_junit_scenarios(RED_ELSEWHERE)))
    assert out.overall_verdict == "request_changes"
    assert [i.severity for i in out.issues] == ["info", "blocking"]


# ─────────────────────────────────────────────────────────────
# Fetching it
# ─────────────────────────────────────────────────────────────
class _Host:
    def __init__(self, conclusion, report=None, raises=False, run_id=42):
        self.conclusion, self.report, self.raises, self.run_id = conclusion, report, raises, run_id
        self.asked = []

    def list_open_prs(self, branch_prefix=""):
        return [{"number": 7, "head_sha": "abc"}]

    def get_workflow_runs(self, workflow_file, branch, limit=20):
        return [{"id": self.run_id, "status": "completed", "conclusion": self.conclusion,
                 "head_sha": "abc"}]

    def get_run_artifact_file(self, run_id, artifact_prefix, filename):
        self.asked.append((run_id, artifact_prefix, filename))
        if self.raises:
            raise RuntimeError("boom")
        return self.report


def test_a_red_run_reads_its_junit_report_and_a_green_run_does_not():
    red = _Host("failure", RED_ELSEWHERE)
    ev = runner_evidence_for_head(red, 7, "auto/LIB-1-x", wait_seconds=0)
    assert ev.conclusion == "failure" and ev.scenarios["borrowabookfromitscataloguecard"] == ["passed"]
    assert red.asked == [(42, "pytest-report-", "junit.xml")]
    green = _Host("success", RED_ELSEWHERE)
    assert runner_evidence_for_head(green, 7, "b", wait_seconds=0) == RunnerEvidence("success")
    assert green.asked == []


def test_a_failed_read_is_no_evidence_never_an_error():
    assert runner_evidence_for_head(_Host("failure", raises=True), 7, "b", wait_seconds=0) \
        == RunnerEvidence("failure", None)
    assert runner_evidence_for_head(_Host("failure", run_id=None), 7, "b", wait_seconds=0) \
        == RunnerEvidence("failure", None)


def test_the_github_adapter_returns_the_named_file_from_the_artifact(monkeypatch):
    from integrations import github_client
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    monkeypatch.setenv("GITHUB_REPO", "o/r")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("junit-unit.xml", b"unit")
        zf.writestr("junit.xml", b"app")

    class Art:
        def __init__(self, name):
            self.name, self.expired, self.archive_download_url = name, False, "https://x/zip"

    class Run:
        def get_artifacts(self):
            return [Art("coverage"), Art("pytest-report-99")]

    class Repo:
        def get_workflow_run(self, run_id):
            assert run_id == 99
            return Run()

    class Resp:
        content = buf.getvalue()

        def raise_for_status(self):
            pass

    import requests
    monkeypatch.setattr(requests, "get", lambda url, **kw: Resp())
    client = github_client.GitHubClient()
    client._repo = Repo()
    assert client.get_run_artifact_file(99, "pytest-report-", "junit.xml") == b"app"
    assert client.get_run_artifact_file(99, "pytest-report-", "missing.xml") is None
    assert client.get_run_artifact_file(99, "nope-", "junit.xml") is None


# ─────────────────────────────────────────────────────────────
# The helpers the diff calls, as the reviewer sees them
# ─────────────────────────────────────────────────────────────
BASE = '''
class BasePage:
    def click_in_row(self, row_locator: str, text: str, target_locator: str) -> None:
        """Click a control inside the row containing `text`.

        A control drawn twice in one row (card and hover overlay): the VISIBLE
        one is clicked.
        """

    def is_gone(self, locator: str) -> bool:
        """True once the element is absent."""

    def _private(self):
        """never shown"""
'''


def test_only_the_helpers_the_changed_page_objects_call_are_shown(tmp_path):
    (tmp_path / "pages").mkdir()
    (tmp_path / "pages" / "base_page.py").write_text(BASE, encoding="utf-8")
    files = [
        {"filename": "pages/catalogue_page.py",
         "content": "class CataloguePage(BasePage):\n    def borrow(self, t):\n"
                    "        self.click_in_row(self.sel('cards'), t, self.sel('borrow'))\n"},
        {"filename": "tests/step_defs/test_loans.py", "content": "page.is_gone('x')"},
    ]
    block = base_page_helpers_called(files, tmp_path)
    assert "`self.click_in_row(row_locator: str, text: str, target_locator: str) -> None`" in block
    assert "the VISIBLE\none is clicked" in block
    assert "is_gone" not in block and "_private" not in block


def test_a_patch_only_file_is_read_from_its_added_lines(tmp_path):
    (tmp_path / "pages").mkdir()
    (tmp_path / "pages" / "base_page.py").write_text(BASE, encoding="utf-8")
    files = [{"filename": "pages/loan_page.py",
              "patch": "@@ -1 +1 @@\n-        self.click_in_row(a, b, c)\n"
                       "+        return self.is_gone(self.sel('fine'))\n"}]
    block = base_page_helpers_called(files, tmp_path)
    assert "self.is_gone(" in block and "click_in_row" not in block


def test_nothing_to_show_is_an_empty_section(tmp_path):
    assert base_page_helpers_called([{"filename": "pages/x.py", "content": "self.go()"}],
                                    tmp_path) == ""


def test_the_prompt_carries_both_sections_and_the_run_uses_the_evidence():
    import inspect

    from agents import agent3_reviewer
    from config.paths import PROMPTS_DIR
    text = (PROMPTS_DIR / "agent3_reviewer.md").read_text(encoding="utf-8")
    assert "{base_page_helpers_section}" in text and "- `scenario`:" in text
    source = inspect.getsource(agent3_reviewer.run)
    assert "runner_evidence_for_head(" in source and "{base_page_helpers_section}" in source


def test_with_a_diff_only_the_added_lines_count(tmp_path):
    """A helper the file called before this change is not under review."""
    (tmp_path / "pages").mkdir()
    (tmp_path / "pages" / "base_page.py").write_text(BASE, encoding="utf-8")
    files = [{"filename": "pages/loan_page.py",
              "content": "self.click_in_row(a, b, c)\nself.is_gone(x)\n",
              "patch": "@@ -1 +1,2 @@\n self.click_in_row(a, b, c)\n+self.is_gone(x)\n"}]
    block = base_page_helpers_called(files, tmp_path)
    assert "self.is_gone(" in block and "click_in_row" not in block
