"""P3 end to end: two nights on main, through every step that runs in CI.

Night 1: the run (one test broken, one flaky, one stopped by an outage), the
retry, scripts/finalise_junit.py, the job's verdict, the triage, the health
check. Night 2: everything passes. Checks F-7, F-19, F-21/F-22 and F-23 where
they meet: the right defect, alert, flake record and picture on the health
issue - and that night 2 closes what night 1 opened, posting once each.

Real JiraClient over a fake Jira, real junit files and scripts; only the repo
host (workflow runs) and the model probe are stand-ins. Generic names only.
"""
import datetime as dt
from pathlib import Path
from types import SimpleNamespace

import pytest

from core import defects
from core import health_checks as hc
from core import pipeline_health as ph
from scripts import finalise_junit as fj
from scripts import pipeline_health_check as health
from scripts import triage_failures as tf
from tests.sandbox.fake_jira import FakeJira, jira_client_over

NAV_503 = ("AssertionError: Navigation to https://s.example/x returned HTTP 503 (x) after 3 "
           "attempts. The page did not load, so every selector on it will time out.")


def _case(name, failure=None, kind="failure"):
    body = f'<{kind} message="{failure}">{failure}</{kind}>' if failure else ""
    return f'<testcase classname="tests.step_defs.test_shop" name="{name}">{body}</testcase>'


def _write(path, *cases):
    path.write_text(f'<testsuites><testsuite>{"".join(cases)}</testsuite></testsuites>')
    return path


@pytest.fixture
def night(monkeypatch, tmp_path):
    ph.reset_cache()
    fake = FakeJira()
    jira = jira_client_over(fake, monkeypatch)
    features = tmp_path / "features"
    features.mkdir()
    (features / "shop.feature").write_text(
        "Feature: Shop\n\n  # JIRA: SBX-9 (hash: abcdef12) owner: SBX-50\n"
        "  Scenario: Pay for an order\n    Given I am home\n")
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "runner.yml").write_text("on:\n  schedule:\n    - cron: '40 21 * * *'\n")
    runs = {"list": []}
    host = SimpleNamespace(get_workflow_runs=lambda *a, **k: runs["list"],
                           check_access=lambda: {"ok": True, "expires": None})
    monkeypatch.setattr("integrations.tracker.get_tracker", lambda: jira)
    monkeypatch.setattr("integrations.repo_host.get_repo_host", lambda: host)
    monkeypatch.setattr(hc, "check_model", lambda mode: hc.Finding("credential:model", False, "ok"))
    yield fake, jira, features, tmp_path, runs
    ph.reset_cache()


def _bugs(fake):
    return {k: d for k, d in fake.issues.items() if d["issuetype"] == "Bug"}


def test_two_nights(night):
    fake, jira, features, root, runs = night
    reports = root / "reports"
    reports.mkdir()

    # ── night 1: the run, then the retry of its three failures ──
    junit = _write(reports / "junit.xml",
                   _case("test_pay_for_an_order", "AssertionError: total was 0"),
                   _case("test_browse", "AssertionError: banner missing"),
                   _case("test_search", NAV_503.replace('"', "'")),
                   _case("test_login"))
    assert fj.count_failed(junit) == 3
    _write(reports / "junit-retry.xml",
           _case("test_pay_for_an_order", "AssertionError: total was 0"),
           _case("test_browse"),                                   # flaky
           _case("test_search", NAV_503.replace('"', "'")))       # still unavailable
    assert fj.main([str(junit), "--retry", str(reports / "junit-retry.xml")]) == 0
    code, why = fj.verdict(junit, "1")
    assert code == 1 and why == ("1 failed and 1 not judged (application unavailable) "
                                 "of 4 after the retry")

    out = tf.run(jira, junit, "https://ci/runs/1", features)
    (bug,) = out["raised"]
    assert out["flaky"] == ["tests.step_defs.test_shop::test_browse"]
    assert out["outages"] == ["tests.step_defs.test_shop::test_search"]
    state = defects.state_of(fake.issues[bug]["description"])
    assert (state["test_case"], state["owner"]) == ("SBX-9", "SBX-50")

    runs["list"] = [{"event": "schedule", "status": "completed", "conclusion": "failure"}] * 3
    assert health.main(["--root", str(root)]) == 0
    key = ph.issue_key(jira)
    assert set(ph.open_alerts(jira)) == {tf.OUTAGE, "workflow-failing:runner.yml"}
    desc = fake.issues[key]["description"]
    assert "Open alerts (2)" in desc and "|{{tests.step_defs.test_shop::test_browse}}|1|" in desc

    # ── night 2: everything passes ──
    _write(junit, _case("test_pay_for_an_order"), _case("test_browse"), _case("test_search"),
           _case("test_login"))
    (reports / "junit-retry.xml").unlink()
    fj.main([str(junit), "--retry", str(reports / "junit-retry.xml")])
    assert fj.verdict(junit, "0") == (0, "all 4 tests passed")
    out = tf.run(jira, junit, "https://ci/runs/2", features)
    assert out["raised"] == [] and out["passing"] == [bug]
    runs["list"] = [{"event": "schedule", "status": "completed", "conclusion": "success"}] + \
        runs["list"]
    health.main(["--root", str(root)])
    assert ph.open_alerts(jira) == {}
    assert "Open alerts (0)" in fake.issues[key]["description"]
    heads = [c.splitlines()[0] for c in fake.comments[key]]
    assert sorted(heads) == sorted([f"[health:open] {tf.OUTAGE}",
                                    "[health:open] workflow-failing:runner.yml",
                                    f"[health:resolved] {tf.OUTAGE}",
                                    "[health:resolved] workflow-failing:runner.yml"]), \
        "each alert: one comment to open, one to close"
    assert len(fake.comments[bug]) == 1 and "Suggest closing" in fake.comments[bug][0]
    assert fake.issues[bug]["status"] == "To Do", "a person closes it"
    assert len(_bugs(fake)) == 1
