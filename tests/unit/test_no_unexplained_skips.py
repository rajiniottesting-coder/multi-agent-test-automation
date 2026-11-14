"""A unit test that skips in CI tests nothing: Agent 4's unit gate fails on
a skip unless it is a fresh project's ("no page objects committed yet") or a
browser test in a job that installed no browser on purpose
(tests/unit/conftest.py). And the gate installs what the tests need.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from tests.unit.conftest import unexplained_skips

ROOT = Path(__file__).resolve().parents[2]


def test_a_missing_package_or_tool_is_refused():
    skips = [("t::pdf", "Skipped: could not import 'reportlab'"),
             ("t::lint", "Skipped: actionlint not installed")]
    assert unexplained_skips(skips, browser_installed=True) == skips


def test_a_fresh_projects_skip_is_accepted():
    skips = [("t::a", "Skipped: no page objects committed yet - Agent 2 has not run"),
             ("t::b", "Skipped: no app_context modules in this checkout"),
             ("t::c", "Skipped: this inventory declares no multi_match family")]
    assert unexplained_skips(skips, browser_installed=True) == []


def test_a_browser_skip_is_accepted_only_where_no_browser_was_installed():
    skips = [("t::b", "Skipped: no browser to launch here: Error")]
    assert unexplained_skips(skips, browser_installed=False) == []
    assert unexplained_skips(skips, browser_installed=True) == skips


def test_the_gate_installs_what_the_tests_need_and_refuses_skips():
    wf = yaml.safe_load((ROOT / ".github" / "workflows" / "agent4_runner.yml")
                        .read_text(encoding="utf-8"))
    steps = {s.get("name"): s for s in wf["jobs"]["test"]["steps"]}
    assert "pip install -r requirements-unit-tests.txt" in steps["Install Python dependencies"]["run"]
    unit = steps["Framework self-test (unit tests)"]
    assert unit["env"]["UNIT_TESTS_NO_SKIPS"] == "1"
    assert unit["env"]["UNIT_TESTS_BROWSER"] == "${{ steps.browser.outcome == 'success' }}"
    assert steps["Install Playwright browsers"]["id"] == "browser"
    needs = (ROOT / "requirements-unit-tests.txt").read_text(encoding="utf-8")
    assert "-r requirements-reports.txt" in needs and "actionlint" in needs
