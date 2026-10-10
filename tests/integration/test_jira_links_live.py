"""
Live check of link direction against a real Jira (Agent 0 design, A4).

Jira's REST API names link sides in a way that is easy to invert. This test
creates one `impacts` link between two existing issues, reads it back
through the typed query, and removes it again, so the configured direction
(`tracker.link_types.impacts.from_field`) is proven on the real instance.

It WRITES to Jira, so it never runs by accident. Opt in with:

    RUN_TRACKER_INTEGRATION=1 \\
    LIVE_STORY_KEY=SCRUM-187 LIVE_TEST_CASE_KEY=SCRUM-197 \\
    pytest tests/integration/test_jira_links_live.py -v

Pick a story and a test case it does NOT own. The link is removed at the end,
also when an assertion fails.
"""
import os

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_TRACKER_INTEGRATION") != "1"
    or not os.getenv("LIVE_STORY_KEY") or not os.getenv("LIVE_TEST_CASE_KEY"),
    reason="live Jira test: set RUN_TRACKER_INTEGRATION=1, LIVE_STORY_KEY, LIVE_TEST_CASE_KEY",
)


def test_impacts_link_reads_from_the_story_side():
    from integrations.jira_client import JiraClient

    jira = JiraClient()
    story, test_case = os.environ["LIVE_STORY_KEY"], os.environ["LIVE_TEST_CASE_KEY"]
    owned_before = {c["key"] for c in jira.get_linked_test_cases(story)}
    try:
        jira.link_issues(story, test_case, "impacts")

        impacted = {c["key"] for c in jira.get_impacted_test_cases(story)}
        assert test_case in impacted, (
            "the story does not read 'impacts' towards the test case - flip "
            "tracker.link_types.impacts.from_field in config.yaml")

        # The impact link must not make the test case look owned.
        assert {c["key"] for c in jira.get_linked_test_cases(story)} == owned_before

        # Seen from the test case, the story is NOT its parent.
        assert jira.get_parent_story_key(test_case) != story or test_case in owned_before
    finally:
        jira.unlink_issues(story, test_case, "impacts")

    assert test_case not in {c["key"] for c in jira.get_impacted_test_cases(story)}
