"""A story that carries an agent's trigger label but that its scan cannot take
(status or sprint outside the selection) is told why, once per agent and
reason - instead of waiting silently.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace as NS
import pytest


ROOT = Path(__file__).resolve().parents[2]


def _issue(key, status):
    return NS(key=key, fields=NS(status=NS(name=status)))


def test_the_tracker_finds_labelled_stories_outside_the_scope():
    from integrations.jira_client import JiraClient
    jql = []

    def search(q, maxResults=20):
        jql.append(q)
        if q.startswith("key in"):
            return [_issue("AB-2", "Done")]
        return [_issue("AB-1", "To Do"), _issue("AB-2", "Done")]
    c = JiraClient.__new__(JiraClient)
    c.project_key = "AB"
    c._client = NS(enhanced_search_issues=search)
    c.get_active_sprint_name = lambda: "Sprint 7"
    out = c.find_unselected_stories({"issue_type": "Story", "allowed_statuses": ["To Do"],
                                     "required_labels": ["go"], "excluded_labels": ["done"],
                                     "sprint": "auto"})
    assert ('AND (NOT (status in ("To Do")) OR sprint is EMPTY OR NOT (sprint = "Sprint 7"))'
            in jql[0]), "a story with no sprint at all is asked for too (F35)"
    assert 'labels = "go"' in jql[0] and 'labels != "done"' in jql[0]
    assert out[0] == {"key": "AB-1", "status": "To Do", "why": "it is not in the sprint 'Sprint 7'"}
    assert out[1]["key"] == "AB-2" and "status 'Done' is not one of: To Do" in out[1]["why"]


def test_a_selection_without_scope_or_trigger_finds_nothing():
    from integrations.jira_client import JiraClient
    c = JiraClient.__new__(JiraClient)
    c.project_key = "AB"
    c._client = NS(enhanced_search_issues=lambda *a, **k: pytest.fail("no query expected"))
    assert c.find_unselected_stories({"required_labels": ["go"]}) == []
    assert c.find_unselected_stories({"allowed_statuses": ["To Do"]}) == []


class _Notified:
    def __init__(self, found):
        self.found, self.comments = found, {}

    def find_unselected_stories(self, selection, sprint_override=None):
        return self.found

    def get_comments(self, key):
        return list(self.comments.get(key, []))

    def add_comment(self, key, body):
        self.comments.setdefault(key, []).append(body)


def test_each_story_is_told_once_per_agent_and_reason():
    from core.selection_notice import MARKER, notify_unselected
    t = _Notified([{"key": "AB-1", "status": "To Do", "why": "it is not in the sprint 'S'"}])
    sel = {"required_labels": ["go"]}
    assert notify_unselected(t, sel, "Agent X") == [("AB-1", "it is not in the sprint 'S'")]
    notify_unselected(t, sel, "Agent X")
    (body,) = t.comments["AB-1"]
    assert body.startswith(MARKER) and "`go`" in body and "Agent X" in body
    notify_unselected(t, sel, "Agent Y")
    assert len(t.comments["AB-1"]) == 2, "another agent's notice is its own"


def test_a_dry_run_or_a_tracker_without_the_capability_posts_nothing():
    from core.selection_notice import notify_unselected
    t = _Notified([{"key": "AB-1", "status": "Done", "why": "w"}])
    assert notify_unselected(t, {"required_labels": ["go"]}, "A", dry_run=True)
    assert t.comments == {}
    assert notify_unselected(object(), {"required_labels": ["go"]}, "A") == []


def test_both_scans_tell_the_stories_they_cannot_take():
    a1 = (ROOT / "agents" / "agent1_analyst.py").read_text(encoding="utf-8")
    a2 = (ROOT / "agents" / "agent2_coder.py").read_text(encoding="utf-8")
    assert "notify_unselected(jira, selection," in a1
    assert "notify_unselected(jira, sel, name," in a2
