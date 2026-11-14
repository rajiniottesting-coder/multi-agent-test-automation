"""Group B gates: R1 readiness (no draft without acceptance criteria) and R5
approvers (only an allowed person's approval starts coding).

Sandbox: the real JiraClient over the fake Jira; generic names only.
"""
from __future__ import annotations

import pytest

from core import approval
from core.readiness import readiness_problem
from tests.sandbox.fake_jira import FakeJira, jira_client_over

pytestmark = pytest.mark.gates_on


def _change(by, before, after, at="2026-11-14T05:00:00.000+0000"):
    return {"created": at, "author": {"accountId": by, "displayName": by.title()},
            "items": [{"field": "labels", "fromString": before, "toString": after}]}


@pytest.fixture
def jira(monkeypatch):
    fake = FakeJira()
    fake.add("Story", "Story under approval", key="SBX-1", labels=["ai-processed"])
    return fake, jira_client_over(fake, monkeypatch)


# ── R5 ──────────────────────────────────────────────────────

def test_who_added_the_label_last():
    history = [{"at": "1", "by": {"name": "A"}, "items": [{"field": "labels", "from": "",
                                                            "to": "human-approved"}]},
               {"at": "2", "by": {"name": "B"}, "items": [{"field": "labels",
                                                            "from": "human-approved", "to": ""}]},
               {"at": "3", "by": {"name": "C"}, "items": [{"field": "labels", "from": "x",
                                                            "to": "x human-approved"}]}]
    assert approval.last_added_by(history, "human-approved")["name"] == "C"
    assert approval.last_added_by(history[:2], "other") is None


def test_empty_lists_keep_todays_behaviour(jira):
    fake, client = jira
    assert approval.check(client, "SBX-1", "human-approved", {}) == (True, "")
    assert approval.gate(client, [{"key": "SBX-1"}], "human-approved", {}) == [{"key": "SBX-1"}]


def test_a_member_of_an_approver_group_may_approve(jira):
    fake, client = jira
    fake.histories["SBX-1"] = [_change("lead", "ai-processed", "ai-processed human-approved")]
    fake.groups["lead"] = ["approvers-team", "users"]
    ok, why = approval.check(client, "SBX-1", "human-approved",
                             {"approver_groups": ["Approvers-Team"]})
    assert ok and why == ""


def test_a_listed_person_may_approve(jira):
    fake, client = jira
    fake.histories["SBX-1"] = [_change("acc-7", "", "human-approved")]
    assert approval.check(client, "SBX-1", "human-approved", {"approvers": ["acc-7"]})[0]


def test_anyone_else_is_refused_once_and_the_label_removed(jira):
    fake, client = jira
    fake.issues["SBX-1"]["labels"].append("human-approved")
    fake.histories["SBX-1"] = [_change("visitor", "ai-processed", "ai-processed human-approved")]
    fake.groups["visitor"] = ["users"]
    kept = approval.gate(client, [{"key": "SBX-1"}], "human-approved",
                         {"approver_groups": ["approvers-team"]})
    assert kept == []
    assert "human-approved" not in fake.issues["SBX-1"]["labels"]
    (body,) = fake.comments["SBX-1"]
    assert body.startswith(approval.MARKER) and "Visitor" in body
    assert "not an allowed approver" in body


def test_no_approval_in_the_history_is_refused(jira):
    fake, client = jira
    ok, why = approval.check(client, "SBX-1", "human-approved", {"approvers": ["x"]})
    assert not ok and "no 'human-approved' label" in why


def test_a_tracker_without_history_is_refused_when_a_list_is_set():
    class NoHistory:
        pass
    ok, why = approval.check(NoHistory(), "SBX-1", "human-approved", {"approvers": ["x"]})
    assert not ok and "cannot be read" in why


def test_agent2_gates_every_pass_and_a_run_by_key():
    from pathlib import Path
    src = (Path(__file__).resolve().parents[2] / "agents" / "agent2_coder.py").read_text()
    assert src.count("approval_gate(jira, ") == 3
    assert "approval_check(get_tracker(), args.story" in src


def test_the_project_names_groups_not_people():
    import yaml
    from config.paths import CONFIG_YAML
    cfg = yaml.safe_load(open(CONFIG_YAML))["agents"]["agent2_coder"]
    assert cfg["approver_groups"] and cfg["approvers"] == []


# ── R1 ──────────────────────────────────────────────────────

ON = {"readiness": {"require_acceptance_criteria": True}}


def test_a_story_without_criteria_is_not_ready():
    assert readiness_problem({"description": "As a user I want things."}, ON)
    assert readiness_problem({"description": "Intro\n\n*Acceptance criteria:*\n# one\n# two"},
                             ON) == ""
    assert readiness_problem({"description": "no list"}, {}) == "", "off by default"


def test_agent1_hands_a_not_ready_story_back_without_failing_the_scan(monkeypatch):
    import agents.agent1_analyst as a1
    assert "not_ready" in a1._NOT_READY and "not_ready" not in a1._NEEDS_A_PERSON
    why = a1.NEEDS_A_PERSON_WHY["not_ready"].format(n=0, why="No list.")
    assert why.startswith("No list.") and "Product owner" in why
    assert "no model was called" in why
    assert a1.print_summary([{"story_id": "SBX-1", "status": "not_ready",
                              "readiness": "No list."}]) is True


def test_agent1_stops_before_any_model_call(monkeypatch):
    import agents.agent1_analyst as a1

    class T:
        def count_linked_test_cases(self, k):
            return 0

        def get_story(self, k):
            return {"key": k, "summary": "S", "description": "no list", "labels": [],
                    "components": []}
    monkeypatch.setattr(a1, "get_tracker", lambda: T())
    monkeypatch.setattr(a1, "load_agent_config", lambda *a, **k: ON)
    monkeypatch.setattr(a1.AppContext, "load", classmethod(
        lambda cls: type("C", (), {"name": "App", "base_url": "https://app.example"})()))

    def no_model(*a, **k):
        raise AssertionError("a model was called")
    monkeypatch.setattr(a1, "LLMClient", no_model)
    result = a1.run("SBX-1")
    assert result["status"] == "not_ready" and result["test_cases_generated"] == 0
