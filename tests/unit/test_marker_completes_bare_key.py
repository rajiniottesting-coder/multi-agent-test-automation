"""A bare "# JIRA: KEY" the model writes is completed in place, not doubled.

The marker carries a hash, so a hash-less "# JIRA: KEY" comment is not one.
Marker injection used to insert the real marker beside it, leaving two JIRA
lines on every scenario of a generated feature. Generic names only.
"""
from agents.agent2_coder import _inject_markers_into_feature

TCS = [{"key": "PROJ-1", "summary": "Add a widget", "description": "d1", "owner": "PROJ-9"},
       {"key": "PROJ-2", "summary": "Remove a widget", "description": "d2", "owner": "PROJ-9"}]


def _jira_lines(text):
    return [l.strip() for l in text.splitlines() if "JIRA" in l]


def test_a_bare_key_comment_becomes_the_marker():
    feature = ("Feature: Widgets\n\n  @smoke\n  # JIRA: PROJ-1\n  Scenario: Add a widget\n    When x\n\n"
               "  # JIRA: PROJ-2\n  @edge\n  Scenario: Remove a widget\n    When y\n")
    lines = _jira_lines(_inject_markers_into_feature(feature, TCS))
    assert len(lines) == 2
    assert lines[0].startswith("# JIRA: PROJ-1 (hash: ") and lines[0].endswith("owner: PROJ-9")
    assert lines[1].startswith("# JIRA: PROJ-2 (hash: ")


def test_without_a_bare_comment_the_marker_is_inserted_as_before():
    feature = ("Feature: Widgets\n\n  Scenario: Add a widget\n    When x\n\n"
               "  Scenario: Remove a widget\n    When y\n")
    lines = _jira_lines(_inject_markers_into_feature(feature, TCS))
    assert [l.split(" (")[0] for l in lines] == ["# JIRA: PROJ-1", "# JIRA: PROJ-2"]


def test_a_bare_comment_for_another_key_is_left_alone():
    feature = ("Feature: Widgets\n\n  # JIRA: OTHER-7\n  Scenario: Add a widget\n    When x\n\n"
               "  Scenario: Remove a widget\n    When y\n")
    lines = _jira_lines(_inject_markers_into_feature(feature, TCS))
    assert "# JIRA: OTHER-7" in lines and len(lines) == 3


def test_an_existing_full_marker_is_refreshed_not_doubled():
    feature = ("Feature: Widgets\n\n  # JIRA: PROJ-1 (hash: 00000000) owner: PROJ-9\n"
               "  Scenario: Add a widget\n    When x\n\n  Scenario: Remove a widget\n    When y\n")
    lines = _jira_lines(_inject_markers_into_feature(feature, TCS))
    assert len(lines) == 2 and "00000000" not in lines[0]
