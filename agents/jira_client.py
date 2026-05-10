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
        # JIRA_PROJECT_KEY is REQUIRED (no silent fallback).
        # A misconfigured deployment that quietly defaults to a wrong project
        # is far worse than failing fast with a clear error.
        self.project_key = os.getenv("JIRA_PROJECT_KEY")
        self._client: Optional[JIRA] = None

        if not all([self.url, self.email, self.token, self.project_key]):
            missing = [
                name for name, val in [
                    ("JIRA_URL", self.url),
                    ("JIRA_EMAIL", self.email),
                    ("JIRA_API_TOKEN", self.token),
                    ("JIRA_PROJECT_KEY", self.project_key),
                ] if not val
            ]
            raise RuntimeError(
                f"JiraClient: missing required env var(s): {', '.join(missing)}. "
                f"See .env.example or docs/CONFIGURATION.md."
            )

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
        """Create a 'Relates' link between Test Case and Story.

        Note: failures here are NOT silently swallowed. A missing link means
        Agent 2 won't find the test cases later (it queries by linkedIssues).
        We log at ERROR level and re-raise — the caller can decide whether
        to abort the batch or continue with a partial result.
        """
        from jira.exceptions import JIRAError
        try:
            self.client.create_issue_link(
                type="Relates",
                inwardIssue=test_case_key,
                outwardIssue=story_key,
            )
            logger.info(f"Linked {test_case_key} → {story_key}")
        except JIRAError as e:
            logger.error(
                f"Failed to link {test_case_key} → {story_key}: "
                f"{e.status_code} {e.text}. Agent 2 may not find this test "
                f"case when scanning for linked issues."
            )
            raise

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

    def remove_label(self, issue_key: str, label: str) -> None:
        """
        Remove a label from a Jira issue (preserves other labels). Idempotent
        — if the label isn't present, this is a no-op rather than an error.

        Used by Phase 6's regeneration flow: after Agent 2 successfully
        regenerates code, we remove the `ai-regenerate` label so it acts
        as a one-shot signal rather than persistent state. Without this
        cleanup, the story would re-trigger regeneration on every scan.
        """
        issue = self.client.issue(issue_key)
        current_labels = list(issue.fields.labels)
        if label in current_labels:
            current_labels.remove(label)
            issue.update(fields={"labels": current_labels})
            logger.info(f"Removed label '{label}' from {issue_key}")
        else:
            logger.info(f"Label '{label}' not on {issue_key} — nothing to remove")

    def add_comment(self, issue_key: str, body: str) -> str:
        """Post a comment on a Jira issue and return the comment URL.

        Used by Agent 5 (Reporter) to post test run summaries.

        Args:
            issue_key: e.g., "PROJ-123" (any Jira project key + number)
            body: Markdown body of the comment. Jira Cloud renders Markdown
                  reasonably well via the v3 API; for v2 APIs, headings and
                  some formatting may render literally.

        Returns:
            URL to the created comment, suitable for logs and the agent's return value.
        """
        comment = self.client.add_comment(issue_key, body)
        # Comment URL format: https://<site>/browse/<issue>?focusedCommentId=<id>
        comment_url = f"{self.url}/browse/{issue_key}?focusedCommentId={comment.id}"
        logger.info(f"Posted comment on {issue_key}: {comment_url}")
        return comment_url

    def get_parent_story_key(self, issue_key: str) -> Optional[str]:
        """Return the parent Story key for a Test Case, or None if not applicable.

        Used by Agent 5 (Reporter) to ensure run-summary comments land on the
        user-facing Story (e.g. SCRUM-20) instead of the implementation-detail
        Test Case (e.g. SCRUM-23) extracted from a feature branch name.

        Resolution logic:
          - If `issue_key` itself is a Story (or anything that's not a Test Case),
            return None — caller should keep the original key.
          - If `issue_key` is a Test Case, scan its issuelinks for a "Relates"
            link pointing OUT to a Story and return that Story's key.
          - If the test case has no Story-typed parent, return None and let the
            caller fall back. We never raise here — Agent 5 should still post
            *somewhere* even if link resolution fails.
        """
        try:
            issue = self.client.issue(issue_key, fields="issuetype,issuelinks")
        except Exception as e:
            logger.warning(f"Could not fetch {issue_key} for parent lookup: {e}")
            return None

        issue_type = getattr(issue.fields.issuetype, "name", "") or ""
        if issue_type.lower() != "test case":
            # Already a Story (or Bug, Task, etc.) — no walking needed.
            return None

        # create_test_case() builds links as inwardIssue=test_case, outwardIssue=story
        # with type "Relates", so the parent appears on `outwardIssue` of the link.
        for link in getattr(issue.fields, "issuelinks", []) or []:
            outward = getattr(link, "outwardIssue", None)
            if outward is None:
                continue
            outward_type = getattr(outward.fields.issuetype, "name", "") or ""
            if outward_type.lower() == "story":
                logger.info(
                    f"Resolved test-case {issue_key} → parent story {outward.key}"
                )
                return outward.key

        logger.info(
            f"{issue_key} is a Test Case but has no Story-typed outward link; "
            f"will comment on {issue_key} itself."
        )
        return None