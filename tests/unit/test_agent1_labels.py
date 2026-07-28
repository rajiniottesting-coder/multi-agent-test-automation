"""
Unit tests for Agent 1 (Analyst) label lifecycle.

Specifically: after Agent 1 successfully creates test cases for a story,
the trigger label(s) that brought the story into scope (e.g., `ai-ready`)
must be removed from the story. Only `ai-processed` remains as the new
state marker. This keeps Jira label state clean — no stale triggers.
"""

import os
import pytest
from unittest.mock import MagicMock, patch


# Stub env so module imports don't fail on credential checks
for v in (
    "OPENAI_API_KEY", "JIRA_URL", "JIRA_EMAIL", "JIRA_API_TOKEN",
    "JIRA_PROJECT_KEY", "GITHUB_TOKEN", "GITHUB_REPO",
):
    os.environ.setdefault(v, "stub")


@pytest.fixture
def fake_test_case_list():
    """Two minimal test cases the LLM 'produced'."""
    tc1 = MagicMock(test_type="positive", title="logs in successfully")
    tc2 = MagicMock(test_type="negative", title="rejects bad password")
    return MagicMock(test_cases=[tc1, tc2])


@pytest.fixture
def patched_agent1(fake_test_case_list):
    """Patch all of Agent 1's external dependencies. Yields (jira_mock, run_callable)."""
    from agents import agent1_analyst

    mock_jira = MagicMock()
    # A CLEAN story: no Test Cases linked yet. Must be explicit - a bare
    # MagicMock returns a truthy Mock, which the duplicate guard reads as
    # "this story already has test cases" and refuses to run.
    mock_jira.count_linked_test_cases.return_value = 0
    mock_jira.get_story.return_value = {
        "summary": "Login to the site",
        "description": "User can log in...",
    }
    # Each create_test_case returns an issue with a .key
    mock_jira.create_test_case.side_effect = [
        MagicMock(key="SCRUM-100"), MagicMock(key="SCRUM-101"),
    ]

    mock_llm = MagicMock()
    mock_llm.invoke_with_schema.return_value = fake_test_case_list

    # Patch the module-level constructors and prompt loader
    with patch.object(agent1_analyst, "get_tracker", return_value=mock_jira), \
         patch.object(agent1_analyst, "LLMClient", return_value=mock_llm), \
         patch.object(agent1_analyst, "load_prompt", return_value="prompt {story_summary} {story_description}"):
        yield mock_jira, agent1_analyst.run


class TestTriggerLabelCleanup:
    def test_ai_ready_removed_after_successful_run(self, patched_agent1):
        """After a successful Agent 1 run, the trigger label `ai-ready` must
        be removed from the story so the label state is clean."""
        mock_jira, run = patched_agent1
        run("SCRUM-1", dry_run=False)

        # add_label called for 'ai-processed' (completion marker)
        mock_jira.add_label.assert_called_once_with("SCRUM-1", "ai-processed")

        # remove_label called for 'ai-ready' (trigger cleanup)
        mock_jira.remove_label.assert_any_call("SCRUM-1", "ai-ready")

    def test_dry_run_does_not_touch_labels(self, patched_agent1):
        """Dry-run mode must not create test cases AND must not modify labels."""
        mock_jira, run = patched_agent1
        run("SCRUM-1", dry_run=True)

        mock_jira.create_test_case.assert_not_called()
        mock_jira.add_label.assert_not_called()
        mock_jira.remove_label.assert_not_called()

    def test_remove_label_failure_is_non_fatal(self, patched_agent1):
        """If Jira rejects the remove_label call, Agent 1 must still report
        success — the completion marker (ai-processed) is the primary state,
        not the cleanup of ai-ready."""
        mock_jira, run = patched_agent1
        mock_jira.remove_label.side_effect = Exception("Jira API hiccup")

        # Should not raise — non-fatal warning instead
        result = run("SCRUM-1", dry_run=False)
        assert result["status"] == "tests_drafted"
        # And the completion label was still added (run did succeed)
        mock_jira.add_label.assert_called_once_with("SCRUM-1", "ai-processed")