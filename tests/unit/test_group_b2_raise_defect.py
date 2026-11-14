"""Group B D6: a `raise-defect` label on a pull request raises the run's
failures as application defects - as on main, but nothing judged passing from
a pull request's run.

Sandbox: the real JiraClient over the fake Jira; generic names only.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from core import defects
from core import pipeline_health as ph
from scripts import raise_pr_defects as rpd
from tests.sandbox.fake_jira import FakeJira, jira_client_over
from tests.unit.test_defect_triage import _case

BUG = defects.settings()["issue_type"]


def _xml(*cases) -> bytes:
    return f'<testsuites><testsuite>{"".join(cases)}</testsuite></testsuites>'.encode()


class Host:
    def __init__(self, report: bytes | None, status="completed"):
        self.report, self.status = report, status
        self.comments, self.labels_removed = {}, []

    def get_pr_metadata(self, n):
        return {"number": n, "head_branch": "auto/SBX-1-cart", "url": f"https://pr/{n}"}

    def list_open_prs(self, prefix=""):
        return [{"number": 7, "head_sha": "abc", "head_ref": "auto/SBX-1-cart"}]

    def get_workflow_runs(self, workflow, branch, **k):
        return [{"id": 99, "status": self.status, "conclusion": "failure", "head_sha": "abc",
                 "url": "https://ci.example/runs/99"}]

    def get_run_artifact_file(self, run_id, prefix, name):
        return self.report

    def post_pr_comment(self, n, body):
        self.comments.setdefault(n, []).append(body)

    def remove_pr_label(self, n, label):
        self.labels_removed.append((n, label))
        return True


@pytest.fixture
def world(monkeypatch, tmp_path):
    ph.reset_cache()
    fake = FakeJira()
    fake.add("Story", "A shopper keeps a cart", key="SBX-1")
    fake.add("Test Case", "[Positive] Add an item", key="SBX-5")
    jira = jira_client_over(fake, monkeypatch)
    real = defects.section("defects")
    monkeypatch.setattr(defects, "settings", lambda: {**real, "max_new_per_run": 10,
                                                      "link_recurrences": False})
    features = tmp_path / "features"
    features.mkdir()
    (features / "cart.feature").write_text(
        "Feature: Cart\n\n  # JIRA: SBX-5 (hash: abc12345) owner: SBX-1\n"
        "  Scenario: Add an item\n    Given I am home\n\n"
        "  Scenario: Remove an item\n    Given I am home\n")
    yield fake, jira, features
    ph.reset_cache()


def _bugs(fake):
    return {k: d for k, d in fake.issues.items() if d["issuetype"] == BUG}


def test_the_label_raises_the_failure_as_a_defect_and_comes_off(world):
    fake, jira, features = world
    host = Host(_xml(_case("test_add_an_item", "failed"), _case("test_remove_an_item")))
    out = rpd.run(jira, host, 7, features)
    (key,) = out["raised"]
    bug = _bugs(fake)[key]
    assert "fails on pull request #7" in bug["summary"]
    assert "A test fails on pull request #7" in bug["description"]
    assert "labelled the pull request {{raise\\-defect}}" in bug["description"], \
        "rendered for the tracker: monospace, its - escaped"
    assert defects.state_of(bug["description"])["test_case"] == "SBX-5"
    (comment,) = host.comments[7]
    assert comment.startswith(rpd.MARKER) and key in comment and "runs/99" in comment
    assert host.labels_removed == [(7, "raise-defect")]


def test_a_pull_request_run_judges_nothing_passing(world, monkeypatch):
    fake, jira, features = world
    old = fake.add(BUG, "[Auto] remove fails", labels=["ai-defect"],
                   description=defects.render(jira, {
                       "test": "tests.step_defs.test_cart::test_remove_an_item",
                       "cause": "unclassified", "cause_text": "x", "remedy": "y",
                       "failure": "f", "first_seen": "2026-11-01", "last_seen": "2026-11-01",
                       "times": 1, "test_case": None, "owner": "SBX-1"}))
    host = Host(_xml(_case("test_remove_an_item")))
    out = rpd.run(jira, host, 7, features)
    assert out["passing"] == [] and "ai-defect-passing" not in fake.issues[old]["labels"]
    assert "nothing in Agent 4's run" in host.comments[7][0]


def test_no_finished_run_raises_nothing_and_says_so(world):
    fake, jira, features = world
    host = Host(None, status="in_progress")
    out = rpd.run(jira, host, 7, features)
    assert out == {"report": False} and _bugs(fake) == {}
    assert "once *Run Tests* has finished" in host.comments[7][0]
    assert host.labels_removed == [(7, "raise-defect")]


def test_the_workflow_label_is_the_configured_one():
    wf = (Path(__file__).resolve().parents[2] / ".github" / "workflows"
          / "raise_pr_defects.yml").read_text()
    assert f"github.event.label.name == '{defects.settings()['raise_label']}'" in wf
    assert "group: defect-triage" in wf, "never beside the triage on main"
    run_line = [line for line in wf.splitlines() if line.strip().startswith("run: python")][0]
    assert "${{" not in run_line
