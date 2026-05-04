"""
Jira client wrapper — handles all Jira API interactions for our agents.
Centralized so we don't repeat boilerplate everywhere.
"""
import os
import logging
from typing import Optional
from jira import JIRA, Issue
from dotenv import load_dotenv

from agents.schemas import TestCase

load_dotenv()
logger = logging.getLogger(__name__)


class JiraClient:
    """Thin wrapper around the `jira` library, scoped to our project."""

    def __init__(self):
        self.url = os.getenv("JIRA_URL")
        self.email = os.getenv("JIRA_EMAIL")
        self.token = os.getenv("JIRA_API_TOKEN")
        self.project_key = os.getenv("JIRA_PROJECT_KEY", "SCRUM")
        self._client: Optional[JIRA] = None

    @property
    def client(self) -> JIRA:
        """Lazy-init the Jira client (only connects when first accessed)."""
        if self._client is None:
            self._client = JIRA(server=self.url, basic_auth=(self.email, self.token))
        return self._client

    # ─────────────────────────────────────────────────────────────
    # Story selection
    # ─────────────────────────────────────────────────────────────

    def get_story(self, issue_key: str) -> dict:
        """Fetch a single story and return its key fields as a dict."""
        issue = self.client.issue(issue_key)
        logger.info(f"Fetched {issue_key}: {issue.fields.summary}")
        return {
            "key": issue.key,
            "summary": issue.fields.summary,
            "description": issue.fields.description or "",
            "status": issue.fields.status.name,
            "labels": list(issue.fields.labels),
        }

    def find_stories_to_process(self, selection_config: dict, max_results: int = 50) -> list[dict]:
        """
        Find stories matching ALL criteria in selection_config.

        selection_config example:
            {
                "issue_type": "Story",
                "allowed_statuses": ["To Do", "In Progress"],
                "required_labels": ["ai-ready"],
                "excluded_labels": ["ai-processed", "ai-skip"],
            }
        """
        jql_parts = [f'project = {self.project_key}']

        # Issue type
        if issue_type := selection_config.get("issue_type"):
            jql_parts.append(f'issuetype = "{issue_type}"')

        # Allowed statuses (OR within, AND with rest)
        if statuses := selection_config.get("allowed_statuses"):
            status_list = ", ".join(f'"{s}"' for s in statuses)
            jql_parts.append(f"status in ({status_list})")

        # Required labels (each must be present — AND)
        for label in selection_config.get("required_labels", []):
            jql_parts.append(f'labels = "{label}"')

        # Excluded labels (none may be present — AND NOT)
        for label in selection_config.get("excluded_labels", []):
            jql_parts.append(f'labels != "{label}"')

        jql = " AND ".join(jql_parts)
        logger.info(f"Searching Jira with JQL: {jql}")

        # Use the new search API method (Atlassian removed legacy /rest/api/2/search)
        issues = self.client.enhanced_search_issues(jql, maxResults=max_results)

        results = [
            {
                "key": issue.key,
                "summary": issue.fields.summary,
                "description": issue.fields.description or "",
                "status": issue.fields.status.name,
                "labels": list(issue.fields.labels),
            }
            for issue in issues
        ]
        logger.info(f"Found {len(results)} stories matching criteria")
        return results

    # ─────────────────────────────────────────────────────────────
    # Test case creation
    # ─────────────────────────────────────────────────────────────

    def create_test_case(self, test_case: TestCase, parent_story_key: str) -> Issue:
        """Create a 'Test Case' issue in Jira, linked to the parent story."""
        description = self._format_test_case_description(test_case)

        issue_dict = {
            "project": {"key": self.project_key},
            "summary": f"[{test_case.test_type}] {test_case.title}",
            "description": description,
            "issuetype": {"name": "Test Case"},
        }

        new_issue = self.client.create_issue(fields=issue_dict)
        logger.info(f"Created Test Case: {new_issue.key} — {test_case.title}")

        self._link_to_story(new_issue.key, parent_story_key)
        return new_issue

    def _link_to_story(self, test_case_key: str, story_key: str) -> None:
        """Create a 'Relates' link between Test Case and Story."""
        try:
            self.client.create_issue_link(
                type="Relates",
                inwardIssue=test_case_key,
                outwardIssue=story_key,
            )
            logger.info(f"Linked {test_case_key} → {story_key}")
        except Exception as e:
            logger.warning(f"Could not link {test_case_key} to {story_key}: {e}")

    @staticmethod
    def _format_test_case_description(tc: TestCase) -> str:
        """Convert structured TestCase into readable Jira wiki-markup text."""
        lines = [
            f"*Description:* {tc.description}",
            f"*Priority:* {tc.priority}",
            f"*Type:* {tc.test_type}",
            "",
            "*Preconditions:*",
        ]
        if tc.preconditions:
            lines.extend(f"# {p}" for p in tc.preconditions)
        else:
            lines.append("None")

        lines.extend(["", "*Steps:*"])
        for step in tc.steps:
            lines.append(f"# *{step.action}*")
            lines.append(f"   _Expected:_ {step.expected_result}")

        lines.extend(["", f"*Expected Outcome:* {tc.expected_outcome}"])

        if tc.test_data:
            lines.append("")
            lines.append("*Test Data:*")
            for k, v in tc.test_data.items():
                lines.append(f"- *{k}:* {v}")

        return "\n".join(lines)

    # ─────────────────────────────────────────────────────────────
    # Label management
    # ─────────────────────────────────────────────────────────────

    def add_label(self, issue_key: str, label: str) -> None:
        """Add a label to a Jira issue (preserves existing labels)."""
        issue = self.client.issue(issue_key)
        current_labels = list(issue.fields.labels)
        if label not in current_labels:
            current_labels.append(label)
            issue.update(fields={"labels": current_labels})
            logger.info(f"Added label '{label}' to {issue_key}")
        else:
            logger.info(f"Label '{label}' already on {issue_key} — skipped")