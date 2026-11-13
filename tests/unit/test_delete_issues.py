"""Deleting closed tracker issues by key (scripts/delete_issues.py).

Deletion cannot be undone, so every guard is tested: the confirm word, open
issues kept, sub-tasks kept, the key format, the run limit, and a run that
kept any key fails."""
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from scripts import delete_issues as di

ROOT = Path(__file__).resolve().parents[2]


def test_keys_are_parsed_once_each_and_checked():
    assert di.parse_keys("prj-1, PRJ-2 PRJ-1") == ["PRJ-1", "PRJ-2"]
    with pytest.raises(ValueError):
        di.parse_keys("PRJ-1, DROP TABLE")


class Tracker:
    def __init__(self):
        self.asked = []

    def delete_closed_issue(self, key, required_label=None):
        self.asked.append(key)
        self.label = required_label
        if key == "PRJ-2":
            return {"key": key, "summary": "open", "deleted": False, "reason": "not closed"}
        return {"key": key, "summary": "s", "type": "Bug", "deleted": True, "reason": ""}


@pytest.fixture
def tracker(monkeypatch):
    t = Tracker()
    monkeypatch.setattr("integrations.tracker.get_tracker", lambda: t)
    monkeypatch.setattr("config._ensure_env_file_loaded", lambda: None)
    return t


def test_nothing_without_the_confirm_word(tracker, capsys):
    assert di.main(["--keys", "PRJ-1"]) == 1
    assert di.main(["--keys", "PRJ-1", "--confirm", "delete"]) == 1
    assert tracker.asked == [] and "Nothing deleted" in capsys.readouterr().out


def test_too_many_keys_delete_nothing(tracker):
    assert di.main(["--keys", "PRJ-1,PRJ-3", "--confirm", "DELETE", "--max", "1"]) == 1
    assert tracker.asked == []


def test_each_key_is_reported_and_a_kept_one_fails_the_run(tracker, capsys):
    assert di.main(["--keys", "PRJ-1, PRJ-2", "--confirm", "DELETE"]) == 1
    out = capsys.readouterr().out
    assert "deleted  PRJ-1" in out and "KEPT     PRJ-2  - not closed" in out
    assert "1 deleted, 1 kept." in out
    assert di.main(["--keys", "PRJ-1", "--confirm", "DELETE"]) == 0


def _jira(category, subtasks=(), labels=()):
    from integrations.jira_client import JiraClient
    c = JiraClient.__new__(JiraClient)
    deleted = []
    issue = SimpleNamespace(key="PRJ-9", delete=lambda: deleted.append("PRJ-9"), fields=SimpleNamespace(
        summary="s", issuetype=SimpleNamespace(name="Bug"), subtasks=list(subtasks),
        labels=list(labels),
        status=SimpleNamespace(name="X", statusCategory=SimpleNamespace(key=category))))
    c._client = SimpleNamespace(issue=lambda key, fields=None: issue)
    return c, deleted


def test_jira_deletes_only_a_closed_issue_without_subtasks():
    c, deleted = _jira("done")
    assert c.delete_closed_issue("PRJ-9")["deleted"] is True and deleted == ["PRJ-9"]
    c, deleted = _jira("indeterminate")
    r = c.delete_closed_issue("PRJ-9")
    assert r["deleted"] is False and "not closed" in r["reason"] and deleted == []
    c, deleted = _jira("done", subtasks=[object()])
    assert c.delete_closed_issue("PRJ-9")["reason"] == "has sub-tasks" and deleted == []


def test_the_workflow_runs_by_hand_only_and_fails_on_a_kept_key():
    wf = yaml.safe_load((ROOT / ".github/workflows/delete_issues.yml").read_text())
    on = wf.get(True) or wf.get("on")
    assert list(on) == ["workflow_dispatch"]
    step = wf["jobs"]["delete"]["steps"][-1]
    assert step["shell"] == "bash" and "--confirm \"$CONFIRM\"" in step["run"]
    assert "${{" not in step["run"]                 # inputs reach it through env only


# ── D10: only throw-away issues (13 Nov 2026) ────────────────────────────

def test_jira_keeps_a_closed_issue_without_the_throw_away_label():
    c, deleted = _jira("done", labels=["ai-defect"])
    r = c.delete_closed_issue("PRJ-9", required_label="test-data")
    assert r["deleted"] is False and r["reason"] == "no 'test-data' label" and deleted == []
    c, deleted = _jira("done", labels=["ai-defect", "test-data"])
    assert c.delete_closed_issue("PRJ-9", required_label="test-data")["deleted"] is True
    c, deleted = _jira("indeterminate", labels=["test-data"])        # still closed only
    assert c.delete_closed_issue("PRJ-9", required_label="test-data")["deleted"] is False


def test_the_script_asks_for_the_configured_label(tracker, capsys, monkeypatch):
    assert di.main(["--keys", "PRJ-1", "--confirm", "DELETE"]) == 0
    assert tracker.label == "test-data"                 # cleanup.delete_label
    tracker.delete_closed_issue = lambda key, required_label=None: {
        "key": key, "summary": "s", "deleted": False, "reason": f"no '{required_label}' label"}
    assert di.main(["--keys", "PRJ-5", "--confirm", "DELETE"]) == 1
    assert "a real defect is closed, not deleted" in capsys.readouterr().out


def test_the_label_can_be_switched_off(tracker, monkeypatch):
    import core.ops_settings as ops
    real = ops.section
    monkeypatch.setattr(ops, "section", lambda n: {"delete_label": ""} if n == "cleanup" else real(n))
    assert di.main(["--keys", "PRJ-1", "--confirm", "DELETE"]) == 0
    assert tracker.label is None
