"""A test case carries its story's components; a project that rejects them
still gets the test case, and any other failure still surfaces.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest
from core.schemas import TestCase, TestStep


def _tc():
    return TestCase(title="Valid login", description="d", priority="High", test_type="Positive",
                    preconditions=[], steps=[TestStep(step_number=1, action="a",
                                                      expected_result="b")],
                    expected_outcome="ok", test_data=None)


def _client(create_issue):
    from integrations.jira_client import JiraClient
    c = JiraClient.__new__(JiraClient)
    c.project_key = "PROJ"
    c._client = SimpleNamespace(create_issue=create_issue)
    c._link_to_story = MagicMock()
    return c


def test_components_are_sent_with_the_test_case():
    seen = []
    c = _client(lambda fields: seen.append(fields) or SimpleNamespace(key="PROJ-9"))
    assert c.create_test_case(_tc(), "PROJ-1", components=["ModuleA"]).key == "PROJ-9"
    assert seen[0]["components"] == [{"name": "ModuleA"}]


def test_no_components_sends_no_field():
    seen = []
    c = _client(lambda fields: seen.append(fields) or SimpleNamespace(key="PROJ-9"))
    c.create_test_case(_tc(), "PROJ-1")
    assert "components" not in seen[0]


def test_a_rejected_component_still_creates_the_test_case():
    calls = []

    def create(fields):
        calls.append(dict(fields))
        if "components" in fields:
            raise RuntimeError('400 {"errors":{"components":"Component name \'X\' is not valid"}}')
        return SimpleNamespace(key="PROJ-9")

    c = _client(create)
    assert c.create_test_case(_tc(), "PROJ-1", components=["X"]).key == "PROJ-9"
    assert len(calls) == 2 and "components" not in calls[1]
    c._link_to_story.assert_called_once_with("PROJ-9", "PROJ-1")


def test_any_other_failure_still_surfaces():
    def create(fields):
        raise RuntimeError("401 Unauthorized")
    with pytest.raises(RuntimeError, match="401"):
        _client(create).create_test_case(_tc(), "PROJ-1", components=["ModuleA"])


def test_agent1_test_cases_inherit_the_story_components(tmp_path, monkeypatch):
    """Sandbox run: the change story carries components ["Login"]; its new
    test case is created with them."""
    from tests.unit.test_agent2_impact import _hand_over_and_draft, world
    fake, jira, _root = world.__wrapped__(tmp_path, monkeypatch)
    before = set(fake.issues)
    _hand_over_and_draft(jira, {"SBX-11": "approve"})
    new = [k for k in fake.issues if k not in before and fake.issues[k]["issuetype"] == "Test Case"]
    assert new and all(fake.issues[k]["components"] == ["Login"] for k in new)
