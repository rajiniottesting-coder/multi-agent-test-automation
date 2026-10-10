"""
Unit tests for the typed parent lookup (Agent 0 design, step A5).

A test case's parent is the story that OWNS it. Once test cases also carry
`impacts` links from the stories that revised them, following "the first
link to a story" can land the owner's report on the change story.
"""
from tests.unit.test_typed_links import _issue, _link, jira  # noqa: F401  (fixture)


# ─────────────────────────────────────────────────────────────────
# A5 - parent lookup follows ownership only
# ─────────────────────────────────────────────────────────────────
class TestParentLookup:
    def test_both_link_types_resolve_to_the_owner(self, jira):
        jc, client = jira
        # The impacts link is listed FIRST - the old code would have taken it.
        client.issue.return_value = _issue("Test Case", [
            _link("Impacts", inward=("AB-2", "Story")),
            _link("Impacts", outward=("AB-7", "Story")),
            _link("Relates", outward=("AB-1", "Story")),
        ])
        assert jc.get_parent_story_key("AB-3") == "AB-1"

    def test_only_impacts_links_gives_none(self, jira):
        jc, client = jira
        client.issue.return_value = _issue("Test Case", [
            _link("Impacts", outward=("AB-2", "Story"))])
        assert jc.get_parent_story_key("AB-3") is None

    def test_ownership_added_from_the_story_side_is_found(self, jira):
        jc, client = jira
        client.issue.return_value = _issue("Test Case", [
            _link("Relates", inward=("AB-1", "Story"))])
        assert jc.get_parent_story_key("AB-3") == "AB-1"

    def test_relates_to_a_non_story_is_ignored(self, jira):
        jc, client = jira
        client.issue.return_value = _issue("Test Case", [
            _link("Relates", outward=("AB-8", "Bug")),
            _link("Relates", outward=("AB-1", "Story")),
        ])
        assert jc.get_parent_story_key("AB-3") == "AB-1"

    def test_a_story_returns_none(self, jira):
        jc, client = jira
        client.issue.return_value = _issue("Story", [])
        assert jc.get_parent_story_key("AB-1") is None
