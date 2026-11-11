"""A temporary HTTP error from the application under test is retried, never a real failure.

L14: from CI the application answers some requests with 503 in short bursts
while it loads fine in a browser. One run failed five of seventeen tests that
way - four page loads and one add-to-cart request - none of them for anything
the change did. BasePage.navigate() now retries a 5xx/429 page load, and Agent 4
re-runs a test whose failure names one; a 4xx, an assertion or a timeout is
never retried.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from pages.base_page import BasePage
from scripts import collapse_junit_reruns

ROOT = Path(__file__).resolve().parents[2]


class _Response:
    def __init__(self, status):
        self.status, self.ok = status, 200 <= status < 400
        self.status_text = "" if status != 200 else "OK"


class _Page:
    def __init__(self, *statuses):
        self.statuses, self.waits, self.visits = list(statuses), [], 0

    def goto(self, url, wait_until=None):
        self.visits += 1
        status = self.statuses.pop(0)
        return None if status is None else _Response(status)

    def wait_for_timeout(self, ms):
        self.waits.append(ms)


@pytest.fixture
def delays(monkeypatch):
    monkeypatch.setattr(BasePage, "_NAV_RETRY_CACHE", (3000, 8000))


@pytest.mark.parametrize("statuses, waits", [
    ((503, 200), [3000]),
    ((503, 502, 200), [3000, 8000]),
    ((429, 200), [3000]),
    ((200,), []),
    ((None,), []),
])
def test_a_temporary_error_is_retried_until_the_page_loads(delays, statuses, waits):
    page = _Page(*statuses)
    BasePage(page).navigate("https://library.example/catalogue")
    assert page.waits == waits and page.visits == len(statuses)


def test_an_outage_that_outlasts_the_retries_fails_and_says_so(delays):
    page = _Page(503, 503, 503)
    with pytest.raises(AssertionError, match=r"returned HTTP 503 \(\) after 3 attempts"):
        BasePage(page).navigate("https://library.example/catalogue")
    assert page.waits == [3000, 8000]


def test_a_4xx_is_an_answer_and_fails_at_once(delays):
    page = _Page(404)
    with pytest.raises(AssertionError, match=r"returned HTTP 404 \(\)\. The page"):
        BasePage(page).navigate("https://library.example/gone")
    assert page.waits == [] and page.visits == 1


def test_an_empty_list_turns_the_retry_off(monkeypatch):
    monkeypatch.setattr(BasePage, "_NAV_RETRY_CACHE", ())
    page = _Page(503)
    with pytest.raises(AssertionError, match=r"HTTP 503 \(\)\. The page"):
        BasePage(page).navigate("https://library.example/catalogue")


def test_the_delays_come_from_config(monkeypatch):
    monkeypatch.setattr(BasePage, "_NAV_RETRY_CACHE", None)
    assert BasePage._navigation_retry_delays_ms() == (3000, 8000)


# ─────────────────────────────────────────────────────────────
# Agent 4: re-run only on a temporary HTTP error
# ─────────────────────────────────────────────────────────────
WORKFLOW = (ROOT / ".github" / "workflows" / "agent4_runner.yml").read_text(encoding="utf-8")


def _only_rerun() -> re.Pattern:
    m = re.search(r'--only-rerun "([^"]+)"', WORKFLOW)
    assert m, "agent4_runner.yml no longer re-runs on a temporary HTTP error"
    return re.compile(m.group(1))


@pytest.mark.parametrize("message, rerun", [
    ("AssertionError: Navigation to https://library.example/x returned HTTP 503 () after 3 attempts.", True),
    ("AssertionError: `#loanModal` is PRESENT in the DOM but HIDDEN ... GET "
     "https://library.example/borrow/1 - HTTP 503.", True),
    ("AssertionError: Navigation to https://library.example/x returned HTTP 429 (Too Many Requests)", True),
    ("AssertionError: Navigation to https://library.example/x returned HTTP 404 ()", False),
    ("AssertionError: Expected 1 loan for 'Dune', got 2", False),
    ("TimeoutError: Locator.click: Timeout 30000ms exceeded", False),
    ("AssertionError: expected HTTP 5000 ms wait", False),
])
def test_only_a_temporary_http_error_is_rerun(message, rerun):
    assert bool(_only_rerun().search(message)) is rerun


def test_the_report_is_collapsed_after_every_run_and_the_plugin_is_pinned():
    assert "--reruns 2" in WORKFLOW
    step = WORKFLOW.split("python -m scripts.collapse_junit_reruns reports/junit.xml")[0]
    assert "if: always()" in step.rsplit("- name:", 1)[1]
    assert re.search(r"^pytest-rerunfailures==", (ROOT / "requirements.txt").read_text(), re.M)


# ─────────────────────────────────────────────────────────────
# One testcase per test, whatever the plugin writes
# ─────────────────────────────────────────────────────────────
DUPLICATED = """<?xml version="1.0"?>
<testsuites><testsuite name="pytest" tests="5" failures="1" errors="0" skipped="0">
<testcase classname="tests.step_defs.test_loans" name="test_borrow_a_book"/>
<testcase classname="tests.step_defs.test_loans" name="test_borrow_a_book"/>
<testcase classname="tests.step_defs.test_loans" name="test_return_a_book"/>
<testcase classname="tests.step_defs.test_loans" name="test_return_a_book"><failure message="x"/></testcase>
<testcase classname="tests.step_defs.test_fines" name="test_pay_a_fine"/>
</testsuite></testsuites>"""


def test_a_rerun_test_keeps_only_its_final_attempt(tmp_path):
    path = tmp_path / "junit.xml"
    path.write_text(DUPLICATED, encoding="utf-8")
    assert collapse_junit_reruns.main([str(path)]) == 0
    suite = next(ET.parse(path).getroot().iter("testsuite"))
    cases = [(c.get("name"), [x.tag for x in c]) for c in suite.iter("testcase")]
    assert cases == [("test_borrow_a_book", ["properties"]),
                     ("test_return_a_book", ["properties", "failure"]),
                     ("test_pay_a_fine", [])]
    assert (suite.get("tests"), suite.get("failures")) == ("3", "1")
    props = suite.find("testcase/properties/property")
    assert (props.get("name"), props.get("value")) == ("reruns", "1")


def test_the_reporter_counts_each_test_once_after_collapsing(tmp_path):
    from agents.agent5_reporter import parse_junit_xml
    path = tmp_path / "junit.xml"
    path.write_text(DUPLICATED, encoding="utf-8")
    collapse_junit_reruns.main([str(path)])
    report = parse_junit_xml(path)
    assert (report.total, report.passed, report.failed) == (3, 2, 1)


def test_nothing_to_collapse_leaves_the_file_alone(tmp_path):
    path = tmp_path / "junit.xml"
    text = DUPLICATED.replace('name="test_borrow_a_book"/>\n<testcase classname="tests.step_defs.test_loans" '
                              'name="test_borrow_a_book"/>', 'name="test_borrow_a_book"/>')
    text = text.replace('<testcase classname="tests.step_defs.test_loans" name="test_return_a_book"/>\n', "")
    path.write_text(text, encoding="utf-8")
    collapse_junit_reruns.main([str(path)])
    assert path.read_text(encoding="utf-8") == text


@pytest.mark.parametrize("content", [None, "<not xml"])
def test_a_missing_or_broken_report_never_fails_the_step(tmp_path, content):
    path = tmp_path / "junit.xml"
    if content is not None:
        path.write_text(content, encoding="utf-8")
    assert collapse_junit_reruns.main([str(path)]) == 0


# ─────────────────────────────────────────────────────────────
# A re-run is recorded whatever shape the plugin's report has
# (11 Nov 2026: pytest-rerunfailures 16 writes only the final attempt, and
# the step printed "no re-run tests" for a test re-run after an HTTP 503)
# ─────────────────────────────────────────────────────────────
def test_the_installed_plugin_records_the_rerun_at_the_source(tmp_path):
    import subprocess
    import sys
    (tmp_path / "test_once.py").write_text(
        "import pathlib\n"
        "M = pathlib.Path(__file__).with_name('mark')\n"
        "def test_refused_once():\n"
        "    if not M.exists():\n"
        "        M.write_text('1')\n"
        "        raise AssertionError('Navigation to https://x.example/ returned HTTP 503 () "
        "after 3 attempts.')\n"
        "def test_clean():\n"
        "    pass\n", encoding="utf-8")
    junit = tmp_path / "junit.xml"
    done = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "core.rerun_record",
         "--rootdir", str(tmp_path), "-c", "/dev/null", str(tmp_path / "test_once.py"),
         "--reruns", "1", "--only-rerun", r"HTTP (5[0-9][0-9]|429)\b", f"--junitxml={junit}"],
        capture_output=True, text=True, cwd=ROOT, env={**__import__("os").environ, "PYTHONPATH": str(ROOT)})
    assert done.returncode == 0, done.stdout + done.stderr
    assert collapse_junit_reruns.recorded(ET.parse(junit).getroot()) == {
        "test_once::test_refused_once": 1}


def test_a_recorded_rerun_is_listed_without_collapsing(tmp_path, capsys):
    path = tmp_path / "junit.xml"
    path.write_text('<testsuites><testsuite tests="2"><testcase classname="c" name="a">'
                    '<properties><property name="reruns" value="2"/></properties></testcase>'
                    '<testcase classname="c" name="b"/></testsuite></testsuites>', encoding="utf-8")
    before = path.read_text(encoding="utf-8")
    assert collapse_junit_reruns.main([str(path)]) == 0
    assert "re-run 2 time(s) after a temporary HTTP error: c::a" in capsys.readouterr().out
    assert path.read_text(encoding="utf-8") == before, "nothing to collapse, nothing rewritten"


def test_the_e2e_run_registers_the_recorder():
    text = (ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")
    assert "config.pluginmanager.register(rerun_record" in text
