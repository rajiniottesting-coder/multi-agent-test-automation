"""F-7: a test the application's outage stopped is reported apart from test failures.

Before: a failure that outlasted the retries (#213, #215) - a page load refused
with HTTP 503 every time, an action request never answered successfully - was
counted as a failed test in the run summary and in Agent 5's report, and read
like a defect in the change.

Now scripts/finalise_junit.py marks it `outage` in junit.xml once
(core/junit_marks.py), and every reader asks that mark: the run summary and
Agent 5 list such tests apart ("not judged"), Agent 5's verdict is
'unavailable' when nothing else failed, Agent 3 takes the run as evidence
neither way, and an owning story's result line says "not judged". The mark is
read from the failure text only - never from a captured log, which may hold a
retried page load that succeeded beside a real failure.
"""
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

import agents.agent5_reporter as a5
from core import junit_marks as jm
from core.failure_diagnosis import diagnose, diagnose_with_context, is_outage
from core.schemas import JiraCommentDraft, RunReport
from core.schemas import TestResult as Result
from pages.base_page import BasePage
from scripts import finalise_junit

ROOT = Path(__file__).resolve().parents[2]
NAV_503 = ("AssertionError: Navigation to https://shop.example/cart returned HTTP 503 "
           "(Service Unavailable) after 3 attempts. The page did not load, so every "
           "selector on it will time out.")
ACTION_503 = ("ApplicationUnavailableError: AssertionError: row not found\n\nWhile this test "
              "ran, the application answered these requests with a temporary server error "
              "and never answered the same request successfully afterwards: POST "
              "https://shop.example/add - HTTP 503.")


# ── the classification ───────────────────────────────────────

@pytest.mark.parametrize("text, outage", [
    (NAV_503, True),
    (ACTION_503, True),
    (NAV_503.replace("503 (Service Unavailable)", "429 (Too Many Requests)"), True),
    ("Error: page.goto: net::ERR_CONNECTION_REFUSED at https://shop.example/", True),
    ("Error: page.goto: net::ERR_NAME_NOT_RESOLVED at https://shop.example/", True),
    (NAV_503.replace("503 (Service Unavailable)", "404 (Not Found)"), False),
    ("AssertionError: Expected 1 item, got 2", False),
    ("TimeoutError: Locator.click: Timeout 30000ms exceeded", False),
    # network evidence of an aborted third-party request is not an outage
    ("AssertionError: hidden. Requests: GET https://ads.example/x - no response "
     "(net::ERR_ABORTED)", False),
    # a retried page load that later succeeded, in a log line
    ("assert False\nWARNING Navigation to https://shop.example/a returned HTTP 503 (x); "
     "retrying in 3000 ms (attempt 2 of 3).", False),
])
def test_what_counts_as_an_outage(text, outage):
    assert is_outage(text) is outage


def test_the_real_navigation_error_is_an_outage(monkeypatch):
    """The message BasePage.navigate actually raises, not a copy of it."""
    class Page:
        def goto(self, url, wait_until=None):
            return type("R", (), {"status": 503, "ok": False, "status_text": "Service Unavailable"})()

        def wait_for_timeout(self, ms):
            pass
    monkeypatch.setattr(BasePage, "_NAV_RETRY_CACHE", (1, 1))
    with pytest.raises(AssertionError) as raised:
        BasePage(Page()).navigate("https://shop.example/cart")
    assert is_outage(str(raised.value))
    assert diagnose(str(raised.value)).label == "application temporarily unavailable"


def test_the_real_restated_action_error_is_an_outage():
    from pages.base_page import with_server_errors
    restated = with_server_errors(AssertionError("row not found"),
                                  ["POST https://shop.example/add - HTTP 503"])
    assert is_outage(f"{type(restated).__name__}: {restated}")


def test_a_log_line_never_reclassifies_a_real_failure():
    log = "WARNING Navigation to https://s/a returned HTTP 503 (x); retrying in 3000 ms"
    assert diagnose_with_context("assert False", log).label == "unclassified"


# ── the mark in junit.xml ────────────────────────────────────

JUNIT = """<?xml version="1.0"?><testsuites><testsuite tests="4" failures="2" errors="1" skipped="0">
<testcase classname="tests.step_defs.test_cart" name="test_add"><failure message="{nav}">{nav}</failure>
<system-out>log</system-out></testcase>
<testcase classname="tests.step_defs.test_cart" name="test_remove"><failure message="AssertionError: Expected 1 item, got 2">tb</failure></testcase>
<testcase classname="tests.step_defs.test_cart" name="test_view"/>
<testcase classname="tests.step_defs.test_login" name="test_in"><error message="setup">{action}</error></testcase>
</testsuite></testsuites>""".format(nav=NAV_503.replace('"', "'"), action=ACTION_503)


def _write(tmp_path, text=JUNIT):
    p = tmp_path / "junit.xml"
    p.write_text(text, encoding="utf-8")
    return p


def test_finalise_marks_only_outage_failures(tmp_path):
    p = _write(tmp_path)
    assert finalise_junit.main([str(p)]) == 0
    root = ET.parse(p).getroot()
    marks = {jm.case_id(c): jm.is_outage(c) for c in jm.cases(root)}
    assert marks == {"tests.step_defs.test_cart::test_add": True,
                     "tests.step_defs.test_cart::test_remove": False,
                     "tests.step_defs.test_cart::test_view": False,
                     "tests.step_defs.test_login::test_in": True}


def test_finalise_twice_keeps_one_mark(tmp_path):
    p = _write(tmp_path)
    finalise_junit.main([str(p)])
    finalise_junit.main([str(p)])
    case = jm.cases(ET.parse(p).getroot())[0]
    assert [x.get("name") for x in case.find("properties")] == ["outage"]


@pytest.mark.parametrize("content", [None, "", "<testsuites><testsuite>"])
def test_finalise_never_fails_on_a_missing_or_broken_report(tmp_path, content):
    path = tmp_path / "junit.xml"
    if content is not None:
        path.write_text(content)
    assert finalise_junit.main([str(path)]) == 0


def test_a_passed_case_with_a_stray_mark_is_not_an_outage():
    case = ET.fromstring('<testcase name="t"><properties><property name="outage" value="1"/>'
                         '</properties></testcase>')
    assert jm.is_outage(case) is False


# ── the run summary (the real inline script from the workflow) ───────────

def _summary_script() -> str:
    import yaml
    wf = yaml.safe_load((ROOT / ".github/workflows/agent4_runner.yml").read_text(encoding="utf-8"))
    step = next(s for s in wf["jobs"]["test"]["steps"]
                if "Write test summary" in (s.get("name") or ""))
    m = re.search(r"<<\s*'PYEOF'\n(.*?)\n\s*PYEOF", step["run"], re.S)
    import textwrap
    return textwrap.dedent(m.group(1))


def _summary(tmp_path, junit_path) -> str:
    out = tmp_path / "summary.md"
    env = {**os.environ, "GITHUB_STEP_SUMMARY": str(out),
           "SUMMARY_REPORTS": f"{junit_path}|App Tests (E2E)", "E2E_EVENT": "pull_request"}
    subprocess.run([sys.executable, "-c", _summary_script()], cwd=ROOT, env=env, check=True,
                   capture_output=True)
    return out.read_text(encoding="utf-8")


def test_the_summary_lists_outages_apart(tmp_path):
    p = _write(tmp_path)
    finalise_junit.main([str(p)])
    text = _summary(tmp_path, p)
    assert "1 of 4 tests failed (2 more could not be judged: the application was unavailable)" in text
    assert "| \U0001f310 Application unavailable | 2 |" in text
    assert "| ❌ Failed | 1 |" in text and "| \U0001f4a5 Errored | 0 |" in text
    failures = text.split("### Failures")[1].split("### Application unavailable")[0]
    assert "test_remove" in failures and "test_add" not in failures
    assert "test_add" in text.split("### Application unavailable (not test failures)")[1]


def test_the_summary_when_only_outages_failed(tmp_path):
    p = _write(tmp_path, JUNIT.replace(
        '<failure message="AssertionError: Expected 1 item, got 2">tb</failure>', ""))
    finalise_junit.main([str(p)])
    p.write_text(p.read_text().replace('failures="2"', 'failures="1"'))
    text = _summary(tmp_path, p)
    assert "No test failed, but 2 of 4 could not be judged" in text
    assert "❌" not in text.splitlines()[0]


def test_an_unmarked_report_reads_as_before(tmp_path):
    text = _summary(tmp_path, _write(tmp_path))
    assert "3 of 4 tests failed" in text and "Application unavailable" not in text


# ── Agent 5 ──────────────────────────────────────────────────

def test_agent5_reads_the_mark(tmp_path):
    p = _write(tmp_path)
    finalise_junit.main([str(p)])
    report = a5.parse_junit_xml(p)
    assert [r.name for r in report.results if r.outage] == ["test_add", "test_in"]


def _r(name, status="passed", outage=False, mod="test_story"):
    return Result(name=name, classname=f"tests.step_defs.{mod}", status=status,
                  failure_message="m" if status != "passed" else None, outage=outage)


def _report(*results):
    f = sum(r.status == "failed" for r in results)
    e = sum(r.status == "error" for r in results)
    return RunReport(total=len(results), passed=len(results) - f - e, failed=f, errors=e,
                     results=list(results))


def test_the_verdict():
    out = [_r("a", "failed", True)]
    assert a5._overall_verdict(_report(_r("b"), *out), [], out) == "unavailable"
    assert a5._overall_verdict(_report(_r("b", "failed"), *out), [], out) == "failed"
    assert a5._overall_verdict(_report(_r("b")), [], []) == "passed"
    assert a5._overall_verdict(RunReport(total=1, passed=0, failed=1), []) == "failed", \
        "a report without per-test results is judged on its counts, as before"


def test_an_outage_is_never_an_outside_failure():
    full = _report(_r("mine"), _r("other", "failed", True, mod="test_other"),
                   _r("broken", "failed", mod="test_other"))
    scoped = _report(_r("mine"))
    assert [r.name for r in a5._failures_outside_scope(full, scoped)] == ["broken"]


def test_the_model_sees_only_what_the_run_could_judge():
    rep = a5._without_outages(_report(_r("a"), _r("b", "failed", True), _r("c", "failed")))
    assert (rep.total, rep.passed, rep.failed) == (2, 1, 1)
    plain = _report(_r("a"))
    assert a5._without_outages(plain) is plain


def test_the_comment_warns_and_lists_them():
    body = a5.build_final_comment("prose", _report(_r("a")), outages=[_r("b", "failed", True)])
    assert body.index("Not judged") < body.index("prose") < body.index("not judged: the application")
    assert "`test_story::b`" in body
    assert a5.build_final_comment("p", _report(_r("a"))) == \
        a5.build_final_comment("p", _report(_r("a")), outages=[])


def test_run_end_to_end(monkeypatch, tmp_path, capsys):
    p = _write(tmp_path)
    finalise_junit.main([str(p)])
    monkeypatch.setattr(a5, "get_repo_host", lambda: type("H", (), {
        "get_pr_changed_files": lambda self, n: [{"filename": "tests/step_defs/test_cart.py"}]})())
    monkeypatch.setattr(a5, "load_prompt", lambda: "{run_report_json}")
    seen = {}

    class LLM:
        def __init__(self, *a, **k):
            pass

        def invoke_structured(self, system_prompt, user_prompt, output_schema):
            seen["prompt"] = user_prompt
            return JiraCommentDraft(title="t", body_markdown="1 of 2 failed.")
    monkeypatch.setattr(a5, "LLMClient", LLM)
    result = a5.run("STORY-1", tmp_path, dry_run=True, cli_pr=7)
    printed = capsys.readouterr().out
    assert result["verdict"] == "failed"
    assert (result["total"], result["failed"]) == (2, 1), "the outage is not counted as the story's"
    assert "test_add" not in seen["prompt"] and "test_remove" in seen["prompt"]
    assert "Not judged:** 2 tests" in printed and "test_login::test_in" in printed


# ── Agent 3 and the owners' result lines ─────────────────────

def test_agent3_takes_an_outage_as_no_evidence(tmp_path):
    from agents.agent3_reviewer import parse_junit_scenarios
    p = _write(tmp_path)
    finalise_junit.main([str(p)])
    out = parse_junit_scenarios(p.read_bytes())
    assert out["add"] == ["outage"] and out["remove"] == ["failed"] and out["view"] == ["passed"]


def test_an_owner_reads_not_judged_and_stage_10_does_not_count_it(tmp_path):
    from types import SimpleNamespace
    from core.impact_results import outcomes_by_key
    index = SimpleNamespace(by_key={"T-1": SimpleNamespace(file="cart.feature", title="Add"),
                                    "T-2": SimpleNamespace(file="cart.feature", title="Remove")})
    results = [_r("test_add", "failed", True, mod="test_cart"),
               _r("test_remove", "failed", mod="test_cart")]
    assert outcomes_by_key(results, index, ["T-1", "T-2"]) == {
        "T-1": "not judged (application unavailable)", "T-2": "failed"}


def test_the_workflow_marks_after_collapsing():
    wf = (ROOT / ".github/workflows/agent4_runner.yml").read_text(encoding="utf-8")
    assert wf.index("scripts.collapse_junit_reruns") < wf.index("scripts.finalise_junit") \
        < wf.index("Write test summary")


def test_when_nothing_could_be_judged_the_model_is_not_asked(monkeypatch, tmp_path, capsys):
    only_outage = JUNIT.replace(
        '<failure message="AssertionError: Expected 1 item, got 2">tb</failure>', "") \
        .replace('<testcase classname="tests.step_defs.test_cart" name="test_view"/>', "")
    p = _write(tmp_path, only_outage.replace('name="test_remove"', 'name="test_remove_x"'))
    p.write_text(p.read_text().replace(
        '<testcase classname="tests.step_defs.test_cart" name="test_remove_x"></testcase>', ""))
    finalise_junit.main([str(p)])
    monkeypatch.setattr(a5, "get_repo_host", lambda: type("H", (), {
        "get_pr_changed_files": lambda self, n: []})())
    monkeypatch.setattr(a5, "load_prompt", lambda: "{run_report_json}")

    class LLM:
        def __init__(self, *a, **k):
            pass

        def invoke_structured(self, **k):
            pytest.fail("nothing to summarise - the model must not be called")
    monkeypatch.setattr(a5, "LLMClient", LLM)
    result = a5.run("STORY-1", tmp_path, dry_run=True)
    assert result["verdict"] == "unavailable" and result["total"] == 0
    assert "None of this story's tests could be judged" in capsys.readouterr().out
