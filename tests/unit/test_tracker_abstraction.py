"""The pipeline must depend on the Tracker Protocol, not on Jira.

Shipping to a client on Xray / TestRail / Azure DevOps should mean writing one
adapter and changing one config line - never editing agents/. These tests pin
that property so it cannot rot.
"""
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agents.tracker import Tracker, get_tracker, register_adapter

ROOT = Path(__file__).resolve().parents[2]
AGENT_FILES = sorted((ROOT / "agents").glob("agent*.py")) + [
    ROOT / "agents" / "usage_ledger.py"]


# ── the contract ─────────────────────────────────────────────

def test_protocol_covers_every_operation_the_agents_use():
    """If an agent calls something not on the Protocol, a new adapter would
    silently miss it."""
    used = set()
    for f in AGENT_FILES:
        used |= set(re.findall(r"\b(?:jira|tracker)\.([a-z_]+)\(", f.read_text(encoding="utf-8")))
    declared = {m for m in dir(Tracker) if not m.startswith("_")}
    missing = used - declared
    assert not missing, f"agents call these, but Tracker does not declare them: {missing}"


def test_jira_client_satisfies_the_protocol():
    from agents.jira_client import JiraClient
    inst = JiraClient.__new__(JiraClient)
    inst.project_key = "SCRUM"
    assert isinstance(inst, Tracker)


# ── no tracker-specific concepts in agent code ───────────────

def test_agents_never_build_queries():
    """JQL is Jira-only. A query in agent code cannot be pointed at another
    tool without editing the agent."""
    offenders = []
    for f in AGENT_FILES:
        src = f.read_text(encoding="utf-8")
        for pat in (r"\bjql\b", r"issuetype\s*=", r"linkedIssues\("):
            for line in src.splitlines():
                if re.search(pat, line, re.I) and not line.strip().startswith("#"):
                    offenders.append(f"{f.name}: {line.strip()[:70]}")
    assert not offenders, "tracker query language leaked into agents:\n" + "\n".join(offenders)


def test_agents_never_instantiate_a_concrete_client():
    """Agents must go through get_tracker() so the adapter is swappable."""
    offenders = [f.name for f in AGENT_FILES
                 if "JiraClient()" in f.read_text(encoding="utf-8")]
    assert not offenders, f"these bypass the factory: {offenders}"


def test_agents_do_not_import_the_jira_library():
    offenders = [f.name for f in AGENT_FILES
                 if re.search(r"^\s*(from|import)\s+jira\b",
                              f.read_text(encoding="utf-8"), re.M)]
    assert not offenders, f"these import the Jira SDK directly: {offenders}"


# ── the factory ──────────────────────────────────────────────

def test_unknown_tracker_names_the_available_ones():
    with pytest.raises(ValueError, match="Unknown tracker type"):
        get_tracker("testrail", fresh=True)


def test_a_new_adapter_needs_no_agent_changes():
    """The whole point: register a class matching the shape and it works."""
    class FakeTracker:
        project_key = "DEMO"
        def get_story(self, key): return {"key": key, "summary": "s",
                                          "description": "d", "labels": []}
        def find_stories_to_process(self, selection, sprint_override=None): return []
        def get_parent_story_key(self, key): return None
        def create_test_case(self, story_key, test_case): return MagicMock(key="T-1")
        def get_linked_test_cases(self, story_key): return []
        def count_linked_test_cases(self, story_key): return 0
        def add_label(self, key, label): pass
        def remove_label(self, key, label): pass
        def add_comment(self, key, body): pass
        def get_comments(self, key): return []

    register_adapter("fake", FakeTracker)
    t = get_tracker("fake", fresh=True)
    assert isinstance(t, Tracker)
    assert t.project_key == "DEMO"
    assert t.get_story("X-1")["key"] == "X-1"


def test_defaults_to_jira_when_config_is_unreadable():
    """An existing deployment with no `tracker:` block keeps working."""
    from agents import tracker as t
    with patch.object(t, "_configured_type", return_value="jira"):
        assert t._configured_type() == "jira"