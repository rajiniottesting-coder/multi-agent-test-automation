"""A story without an acceptance-criteria list is not drafted
(core/readiness.py): Agent 1 hands it back to the product owner with one
comment, before any model call, without failing the scan.
"""

from __future__ import annotations

import pytest
from core.readiness import readiness_problem


pytestmark = pytest.mark.gates_on
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
