"""A change story's expected failures do not fail Agent 4's Run Tests check (X6).

A change story's absence test and its revised tests fail until the change is
deployed - the correct red (X4 labels the story `awaiting-deployment`). With
Run Tests a required check, those failures would block the story's own pull
request until the deployment it is waiting for. The verdict now treats a
failure whose story awaits its deployment as expected: the check passes with a
notice naming each test and its story. Every other failure, and every outage,
still fails it. The tracker decides, with the triage's own rule
(core.defects.awaiting_deployment); when it cannot be read, every failure
counts. Generic names only.
"""
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import yaml

from core import defects, deployment
from scripts import finalise_junit as fj

ROOT = Path(__file__).resolve().parents[2]
SETTINGS = {"enabled": True, "story_type": "Story", "pending_label": "awaiting-deployment",
            "deployed_label": "deployed"}


def _case(name, outcome="passed", props=None):
    body = {"passed": "", "failed": '<failure message="AssertionError: boom">tb</failure>'}[outcome]
    p = "".join(f'<property name="{k}" value="{v}"/>' for k, v in (props or {}).items())
    return (f'<testcase classname="tests.step_defs.test_m" name="{name}">'
            + (f"<properties>{p}</properties>" if p else "") + body + "</testcase>")


def _file(tmp_path, *cases):
    p = tmp_path / "junit.xml"
    p.write_text(f'<testsuites><testsuite tests="0">{"".join(cases)}</testsuite></testsuites>')
    return p


A = "tests.step_defs.test_m::a"
B = "tests.step_defs.test_m::b"


# ── the verdict ──────────────────────────────────────────────

def test_only_expected_failures_pass_with_their_story_named(tmp_path):
    p = _file(tmp_path, _case("a", "failed"), _case("b"))
    code, reason = fj.verdict(p, "1", {A: "S-1"})
    assert code == 0
    assert reason == "1 of 2 tests passed and 1 failed as expected (awaiting deployment: S-1)"


def test_a_real_failure_beside_an_expected_one_still_fails(tmp_path):
    p = _file(tmp_path, _case("a", "failed"), _case("b", "failed"))
    code, reason = fj.verdict(p, "1", {A: "S-1"})
    assert code == 1
    assert reason == ("1 failed and 1 failed as expected (awaiting deployment: S-1) "
                      "of 2 after the retry")


def test_an_outage_is_never_expected(tmp_path):
    p = _file(tmp_path, _case("a", "failed", {"outage": "1"}), _case("b"))
    code, reason = fj.verdict(p, "1", {A: "S-1"})
    assert code == 1 and "1 not judged (application unavailable)" in reason


def test_without_expected_failures_the_verdict_reads_as_before(tmp_path):
    p = _file(tmp_path, _case("a", "failed"), _case("b", props={"flaky": "1"}))
    assert fj.verdict(p, "1") == fj.verdict(p, "1", {}) == (1, "1 failed of 2 after the retry")
    p = _file(tmp_path, _case("a", "failed"), _case("b", props={"flaky": "1"}))
    assert fj.verdict(p, "1", {A: "S-2"})[1].endswith("(1 passed only on the retry - flaky)")


def test_pytest_ending_badly_is_never_excused(tmp_path):
    p = _file(tmp_path, _case("a", "failed"))
    assert fj.verdict(p, "2", {A: "S-1"})[0] == 1


# ── the tracker decides, with the triage's rule ──────────────

class _Tracker:
    def __init__(self, pending=("S-1",), revised=None, fail=False):
        self.pending, self.revised, self.fail = pending, revised or {}, fail

    def find_stories_to_process(self, query, max_results=100):
        if self.fail:
            raise RuntimeError("401")
        assert query["required_labels"] == ["awaiting-deployment"]
        assert query["excluded_labels"] == ["deployed"]
        return [{"key": k} for k in self.pending]

    def get_impacted_test_cases(self, key):
        return [{"key": tc} for tc in self.revised.get(key, [])]


@pytest.fixture
def traced(monkeypatch):
    monkeypatch.setattr(deployment, "settings", lambda: dict(SETTINGS))
    table = {A: {"owner": "S-1", "test_case": "TC-1"},
             B: {"owner": "S-7", "test_case": "TC-9"}}
    monkeypatch.setattr(defects, "trace_of", lambda test, *a, **k: table.get(
        test, {"owner": None, "test_case": None}))
    return table


def test_a_test_owned_by_a_pending_story_waits_for_it(traced):
    assert defects.awaiting_deployment(_Tracker(), [A, B], Path("f")) == {A: "S-1"}


def test_a_test_case_a_pending_change_story_revises_waits_for_it(traced):
    t = _Tracker(pending=("S-3",), revised={"S-3": ["TC-9"]})
    assert defects.awaiting_deployment(t, [A, B], Path("f")) == {B: "S-3"}


def test_an_unreadable_tracker_means_every_failure_counts(traced):
    assert defects.awaiting_deployment(_Tracker(fail=True), [A, B], Path("f")) == {}


def test_off_or_nothing_failing_reads_nothing(traced, monkeypatch):
    assert defects.awaiting_deployment(_Tracker(fail=True), [], Path("f")) == {}
    monkeypatch.setattr(deployment, "settings", lambda: {**SETTINGS, "enabled": False})
    assert defects.awaiting_deployment(_Tracker(), [A], Path("f")) == {}


def test_the_triage_and_the_verdict_share_one_rule(traced):
    waiting = deployment.PendingStories(_Tracker())
    assert defects.waits_for(waiting, A, Path("f")) == "S-1"
    assert defects.waits_for(waiting, B, Path("f")) is None
    assert defects.waits_for(None, A, Path("f")) is None
    import inspect
    assert "waits_for(waiting, test, features_dir, tracker, s)" in inspect.getsource(defects.triage)


# ── the command line ─────────────────────────────────────────

def test_main_reads_the_tracker_and_names_each_expected_failure(tmp_path, traced, monkeypatch,
                                                                capsys):
    monkeypatch.setattr("integrations.tracker.get_tracker", lambda: _Tracker())
    p = _file(tmp_path, _case("a", "failed"), _case("b"))
    assert fj.main(["--verdict", str(p), "--exit-code", "1", "--expected-failures"]) == 0
    out = capsys.readouterr().out
    assert f"::notice::Expected to fail until S-1 is deployed: {A}" in out
    assert "E2E passed: 1 of 2 tests passed and 1 failed as expected" in out


def test_main_never_fails_on_the_tracker(tmp_path, traced, monkeypatch, capsys):
    def boom():
        raise RuntimeError("no credentials")
    monkeypatch.setattr("integrations.tracker.get_tracker", boom)
    p = _file(tmp_path, _case("a", "failed"))
    assert fj.main(["--verdict", str(p), "--exit-code", "1", "--expected-failures"]) == 1
    out = capsys.readouterr().out
    assert "::warning::Stories awaiting deployment not read" in out and "E2E failed" in out


def test_without_the_flag_the_tracker_is_not_read(tmp_path, monkeypatch):
    monkeypatch.setattr(fj, "expected_failures", lambda *a, **k: pytest.fail("read"))
    p = _file(tmp_path, _case("a", "failed"))
    assert fj.main(["--verdict", str(p), "--exit-code", "1"]) == 1


def test_an_outage_is_not_looked_up(tmp_path, traced, monkeypatch):
    seen = []
    monkeypatch.setattr("core.defects.awaiting_deployment",
                        lambda tracker, tests, *a, **k: seen.extend(tests) or {})
    monkeypatch.setattr("integrations.tracker.get_tracker", lambda: _Tracker())
    p = _file(tmp_path, _case("a", "failed", {"outage": "1"}), _case("b", "failed"))
    fj.expected_failures(p)
    assert seen == [B]


# ── the workflow ─────────────────────────────────────────────

def test_the_run_tests_check_decides_with_the_tracker():
    wf = yaml.safe_load((ROOT / ".github/workflows/agent4_runner.yml").read_text(encoding="utf-8"))
    job = wf["jobs"]["test"]
    assert job["name"] == "Run Tests", "the check a ruleset requires"
    decide = next(s for s in job["steps"] if s.get("name") == "Decide the E2E result")
    assert decide["run"].rstrip().endswith("--expected-failures")
    assert set(decide["env"]) == {"JIRA_URL", "JIRA_EMAIL", "JIRA_API_TOKEN", "JIRA_PROJECT_KEY"}
    assert "secrets." not in decide["run"]
    assert "pull_request" in wf[True] and "paths" not in (wf[True]["pull_request"] or {}), \
        "every pull request gets the check, or a required one would wait forever"
