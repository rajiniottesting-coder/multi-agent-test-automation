"""
Unit tests for typed links (Agent 0 design, steps A4 and A5).

A test case has exactly one OWNER (`owns`, Relates in Jira) and may carry
any number of IMPACTS links from stories that revised it. Every query the
pipeline makes must ask for one kind, never "any link", or a change story
would count another story's test cases as its own and an owner's report
could land on the change story.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from core.schemas import TestCase, TestStep
from integrations import tracker as tracker_mod
from integrations.jira_client import JiraClient

TestCase.__test__ = False
TestStep.__test__ = False


def _tc(title="Login works", test_type="Positive"):
    return TestCase(title=title, description="d", priority="High",
                    test_type=test_type, preconditions=["p"],
                    steps=[TestStep(step_number=1, action="a", expected_result="e")],
                    expected_outcome="ok", test_data=None)


@pytest.fixture
def jira():
    """A JiraClient with a mocked SDK client and default settings."""
    client = MagicMock()
    jc = JiraClient.__new__(JiraClient)
    jc.project_key = "AB"
    jc.url = "https://example"
    jc.__dict__["_settings_cache"] = {
        "link_types": {k: dict(v) for k, v in tracker_mod._DEFAULT_LINK_TYPES.items()},
        "retired_label": "ai-retired",
    }
    with patch.object(JiraClient, "client", new_callable=PropertyMock, return_value=client):
        yield jc, client


def _link(type_name, outward=None, inward=None, link_id="1"):
    def issue(key, itype):
        return SimpleNamespace(key=key, fields=SimpleNamespace(
            issuetype=SimpleNamespace(name=itype)))
    return SimpleNamespace(
        id=link_id, type=SimpleNamespace(name=type_name),
        outwardIssue=issue(*outward) if outward else None,
        inwardIssue=issue(*inward) if inward else None,
    )


def _issue(itype, links):
    return SimpleNamespace(fields=SimpleNamespace(
        issuetype=SimpleNamespace(name=itype), issuelinks=links))


# ─────────────────────────────────────────────────────────────────
# Settings
# ─────────────────────────────────────────────────────────────────
class TestSettings:
    def test_project_config_declares_both_kinds(self):
        s = tracker_mod.tracker_settings()
        assert s["link_types"]["owns"]["name"] == "Relates"
        assert s["link_types"]["impacts"]["name"] == "Impacts"
        assert s["link_types"]["impacts"]["query"] == "impacts"
        assert s["retired_label"] == "ai-retired"

    def test_missing_config_falls_back_to_defaults(self, tmp_path, monkeypatch):
        import config.paths
        monkeypatch.setattr(config.paths, "CONFIG_YAML", tmp_path / "absent.yaml")
        s = tracker_mod.tracker_settings()
        assert s["link_types"] == tracker_mod._DEFAULT_LINK_TYPES
        assert s["retired_label"] == "ai-retired"

    def test_partial_config_is_merged_over_defaults(self, tmp_path, monkeypatch):
        import config.paths
        cfg = tmp_path / "c.yaml"
        cfg.write_text('tracker:\n  link_types:\n    impacts: { name: "Affects" }\n')
        monkeypatch.setattr(config.paths, "CONFIG_YAML", cfg)
        s = tracker_mod.tracker_settings()
        assert s["link_types"]["impacts"]["name"] == "Affects"
        assert s["link_types"]["impacts"]["query"] == "impacts"     # default kept
        assert s["link_types"]["owns"]["name"] == "Relates"


# ─────────────────────────────────────────────────────────────────
# A4 - typed queries
# ─────────────────────────────────────────────────────────────────
class TestTypedQueries:
    def test_owned_query_asks_for_the_ownership_link_only(self, jira):
        jc, client = jira
        client.enhanced_search_issues.return_value = []
        jc.get_linked_test_cases("AB-1")
        jql = client.enhanced_search_issues.call_args[0][0]
        assert 'linkedIssues("AB-1", "relates to")' in jql
        assert 'issuetype = "Test Case"' in jql

    def test_retired_cases_are_skipped_but_unlabelled_ones_kept(self, jira):
        jc, client = jira
        client.enhanced_search_issues.return_value = []
        jc.get_linked_test_cases("AB-1")
        jql = client.enhanced_search_issues.call_args[0][0]
        assert '(labels is EMPTY OR labels != "ai-retired")' in jql

    def test_impacted_query_asks_for_the_impacts_link(self, jira):
        jc, client = jira
        client.enhanced_search_issues.return_value = [SimpleNamespace(
            key="AB-3", fields=SimpleNamespace(summary="s", description=None))]
        out = jc.get_impacted_test_cases("AB-2")
        jql = client.enhanced_search_issues.call_args[0][0]
        assert 'linkedIssues("AB-2", "impacts")' in jql
        assert "ai-retired" in jql
        assert out == [{"key": "AB-3", "summary": "s", "description": ""}]

    def test_count_uses_the_same_owned_filter(self, jira):
        jc, client = jira
        client.enhanced_search_issues.return_value = [1, 2]
        assert jc.count_linked_test_cases("AB-1") == 2
        jql = client.enhanced_search_issues.call_args[0][0]
        assert '"relates to"' in jql and "ai-retired" in jql

    def test_count_returns_zero_when_settings_are_broken(self, jira):
        jc, client = jira
        jc.__dict__["_settings_cache"] = {"link_types": {}, "retired_label": "x"}
        assert jc.count_linked_test_cases("AB-1") == 0

    def test_configured_names_flow_into_the_query(self, jira):
        jc, client = jira
        jc.link_types["impacts"]["query"] = "affects"
        jc.__dict__["_settings_cache"]["retired_label"] = "gone"
        client.enhanced_search_issues.return_value = []
        jc.get_impacted_test_cases("AB-2")
        jql = client.enhanced_search_issues.call_args[0][0]
        assert '"affects"' in jql and '"gone"' in jql


# ─────────────────────────────────────────────────────────────────
# A4 - link operations
# ─────────────────────────────────────────────────────────────────
class TestLinkOperations:
    def test_impacts_puts_the_story_on_the_inward_side(self, jira):
        """Jira reads `inwardIssue <outward> outwardIssue`: story impacts test."""
        jc, client = jira
        client.issue.return_value = _issue("Story", [])
        jc.link_issues("AB-2", "AB-3", "impacts")
        client.create_issue_link.assert_called_once_with(
            type="Impacts", inwardIssue="AB-2", outwardIssue="AB-3")

    def test_owns_keeps_agent1s_layout(self, jira):
        """Test case inward, story outward - as _link_to_story always did."""
        jc, client = jira
        client.issue.return_value = _issue("Story", [])
        jc.link_issues("AB-1", "AB-3", "owns")
        client.create_issue_link.assert_called_once_with(
            type="Relates", inwardIssue="AB-3", outwardIssue="AB-1")

    def test_create_test_case_links_exactly_as_before(self, jira):
        jc, client = jira
        client.create_issue.return_value = SimpleNamespace(key="AB-9")
        jc.create_test_case(_tc(), parent_story_key="AB-1")
        client.create_issue_link.assert_called_once_with(
            type="Relates", inwardIssue="AB-9", outwardIssue="AB-1")

    def test_link_is_idempotent(self, jira):
        jc, client = jira
        client.issue.return_value = _issue("Story", [
            _link("Impacts", outward=("AB-3", "Test Case"))])
        jc.link_issues("AB-2", "AB-3", "impacts")
        client.create_issue_link.assert_not_called()

    def test_a_link_of_another_type_does_not_count(self, jira):
        jc, client = jira
        client.issue.return_value = _issue("Story", [
            _link("Relates", outward=("AB-3", "Test Case"))])
        jc.link_issues("AB-2", "AB-3", "impacts")
        client.create_issue_link.assert_called_once()

    def test_unlink_removes_only_that_kind(self, jira):
        jc, client = jira
        client.issue.return_value = _issue("Story", [
            _link("Relates", outward=("AB-3", "Test Case"), link_id="10"),
            _link("Impacts", outward=("AB-3", "Test Case"), link_id="11"),
            _link("Impacts", outward=("AB-4", "Test Case"), link_id="12"),
        ])
        jc.unlink_issues("AB-2", "AB-3", "impacts")
        client.delete_issue_link.assert_called_once_with("11")

    def test_unlink_absent_is_noop(self, jira):
        jc, client = jira
        client.issue.return_value = _issue("Story", [])
        jc.unlink_issues("AB-2", "AB-3", "impacts")
        client.delete_issue_link.assert_not_called()

    def test_unknown_kind_is_rejected(self, jira):
        jc, _client = jira
        with pytest.raises(ValueError, match="Unknown link kind"):
            jc.link_issues("AB-2", "AB-3", "blocks")


# ─────────────────────────────────────────────────────────────────
# A4 - update_test_case and create_story
# ─────────────────────────────────────────────────────────────────
class TestWriteOperations:
    def test_update_uses_the_create_formatters(self, jira):
        """Same text as create, so the marker hash compares like for like."""
        jc, client = jira
        issue = MagicMock()
        client.issue.return_value = issue
        tc = _tc("Login works")
        jc.update_test_case("AB-3", tc)
        issue.update.assert_called_once_with(fields={
            "summary": "[Positive] Login works",
            "description": JiraClient._format_test_case_description(tc),
        })

    def test_summary_prefix_is_not_doubled(self):
        assert JiraClient._format_test_case_summary(
            _tc("[Positive] Login works")) == "[Positive] Login works"

    def test_create_story(self, jira):
        jc, client = jira
        client.create_issue.return_value = SimpleNamespace(key="AB-50")
        key = jc.create_story("Drift: login page", "body", ["Login"], ["impact-check"])
        assert key == "AB-50"
        fields = client.create_issue.call_args.kwargs["fields"]
        assert fields["issuetype"] == {"name": "Story"}
        assert fields["components"] == [{"name": "Login"}]
        assert fields["labels"] == ["impact-check"]

    def test_create_story_without_components(self, jira):
        jc, client = jira
        client.create_issue.return_value = SimpleNamespace(key="AB-51")
        jc.create_story("s", "d", [], [])
        assert "components" not in client.create_issue.call_args.kwargs["fields"]


# ─────────────────────────────────────────────────────────────────
# The pipeline's own fake tracker keeps the two kinds apart too
# ─────────────────────────────────────────────────────────────────
def test_memory_tracker_keeps_owned_and_impacted_apart():
    from tests.unit.test_pipeline_tool_agnostic import MemoryTracker
    t = MemoryTracker()
    t.test_cases = {"T1": {"key": "T1", "summary": "a", "description": ""},
                    "T2": {"key": "T2", "summary": "b", "description": ""}}
    t.link_issues("ACME-1", "T1", "owns")
    t.link_issues("ACME-2", "T1", "impacts")
    t.link_issues("ACME-2", "T2", "owns")
    assert [c["key"] for c in t.get_linked_test_cases("ACME-2")] == ["T2"]
    assert [c["key"] for c in t.get_impacted_test_cases("ACME-2")] == ["T1"]
    assert t.count_linked_test_cases("ACME-2") == 1
    assert t.get_parent_story_key("T1") == "ACME-1"
    t.unlink_issues("ACME-2", "T1", "impacts")
    assert t.get_impacted_test_cases("ACME-2") == []
