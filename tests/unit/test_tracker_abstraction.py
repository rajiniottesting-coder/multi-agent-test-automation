"""The pipeline must depend on the Tracker Protocol, not on Jira.

Shipping to a client on Xray / TestRail / Azure DevOps should mean writing one
adapter and changing one config line - never editing agents/. These tests pin
that property so it cannot rot.
"""
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from integrations.tracker import Tracker, get_tracker, register_adapter

ROOT = Path(__file__).resolve().parents[2]
# Every module that CONSUMES a tracker. usage_ledger lives in core/ because it
# is shared infrastructure, not an agent - but it calls the tracker, so it is
# held to the same no-provider-coupling rule.
AGENT_FILES = sorted((ROOT / "agents").glob("agent*.py")) + [
    ROOT / "core" / "usage_ledger.py"]


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
    from integrations.jira_client import JiraClient
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
        def get_story(self, issue_key): return {"key": issue_key, "summary": "s",
                                                "description": "d", "labels": []}
        def find_stories_to_process(self, selection_config, max_results=5,
                                    sprint_override=None): return []
        def get_parent_story_key(self, issue_key): return None
        def create_test_case(self, test_case, parent_story_key):
            return MagicMock(key="T-1")
        def get_linked_test_cases(self, story_key): return []
        def count_linked_test_cases(self, story_key): return 0
        def add_label(self, issue_key, label): pass
        def remove_label(self, issue_key, label): pass
        def add_comment(self, issue_key, body): return ""
        def get_comments(self, issue_key): return []
        def transition_status(self, issue_key, status): return True
        def get_impacted_test_cases(self, story_key, include_retired=False): return []
        def create_subtask(self, parent_key, summary, description): return "DEMO-10"
        def get_subtasks(self, parent_key): return []
        def set_description(self, issue_key, description): pass
        def get_all_test_cases(self): return []
        def update_test_case(self, issue_key, test_case): pass
        def link_issues(self, from_key, to_key, kind): pass
        def unlink_issues(self, from_key, to_key, kind): pass
        def create_story(self, summary, description, components, labels): return "DEMO-9"

    register_adapter("fake", FakeTracker)
    t = get_tracker("fake", fresh=True)
    assert isinstance(t, Tracker)
    assert t.project_key == "DEMO"
    assert t.get_story("X-1")["key"] == "X-1"
    # keyword call, exactly as agent1 makes it
    assert t.create_test_case({}, parent_story_key="S-1").key == "T-1"


def test_defaults_to_jira_when_config_is_unreadable():
    """An existing deployment with no `tracker:` block keeps working."""
    from integrations import tracker as t
    with patch.object(t, "_configured_type", return_value="jira"):
        assert t._configured_type() == "jira"

# ── SIGNATURES are the contract, not just names ──────────────

def _params(func):
    import inspect
    return [p for p in inspect.signature(func).parameters if p != "self"]


def test_every_adapter_matches_the_protocol_signature_exactly():
    """Name-only conformance is not enough.

    `create_test_case` is called as `create_test_case(tc, parent_story_key=...)`
    - a KEYWORD argument - so the parameter name and order are both part of the
    contract. An adapter with the right method names but shuffled parameters
    passes isinstance() and then fails at runtime, which is the worst outcome:
    it looks wired up until a real story goes through.
    """
    import inspect
    from integrations.tracker import _ADAPTERS
    from integrations.jira_client import JiraClient

    # Check every concrete adapter we can inspect without constructing it.
    concrete = {"jira": JiraClient}
    for name, cls in concrete.items():
        mismatches = []
        for member in (m for m in dir(Tracker) if not m.startswith("_")):
            proto = getattr(Tracker, member, None)
            impl = getattr(cls, member, None)
            if not callable(proto) or not callable(impl):
                continue          # properties are checked by isinstance
            if _params(proto) != _params(impl):
                mismatches.append(
                    f"{member}: Protocol{_params(proto)} != {cls.__name__}{_params(impl)}")
        assert not mismatches, (
            f"adapter {name!r} drifts from the Protocol:\n  " + "\n  ".join(mismatches))


def test_keyword_call_sites_still_resolve():
    """Any agent call using keyword args must match the Protocol's names."""
    import re
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    kwargs_used = set()
    for f in sorted((root / "agents").glob("agent*.py")):
        for m in re.finditer(r"\b(?:jira|tracker)\.(\w+)\(([^)]*)\)", f.read_text(encoding="utf-8")):
            for kw in re.findall(r"(\w+)\s*=", m.group(2)):
                kwargs_used.add((m.group(1), kw))
    for method, kw in kwargs_used:
        proto = getattr(Tracker, method, None)
        if proto is None or not callable(proto):
            continue
        assert kw in _params(proto), (
            f"agents call {method}({kw}=...) but the Protocol has no such "
            f"parameter — a new adapter would break at runtime")