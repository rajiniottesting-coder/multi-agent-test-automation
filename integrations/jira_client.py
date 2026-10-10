"""
Jira client wrapper — handles all Jira API interactions for our agents.
Centralized so we don't repeat boilerplate everywhere.
"""
import os
import logging
from typing import Optional
from jira import JIRA, Issue
from dotenv import load_dotenv

from core.schemas import TestCase
from integrations.tracker import tracker_settings

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
        # JIRA_BOARD_ID is OPTIONAL — required only when config.yaml uses
        # sprint: "auto". Set once in .env / GitHub secrets; it never changes
        # unless you move to a different Jira board.
        self.board_id = os.getenv("JIRA_BOARD_ID")
        self._client: Optional[JIRA] = None
        # Cache so multiple scan passes in one run make only one API call.
        self._active_sprint_cache: Optional[str] = None

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
                f"See .env.example or docs/GUIDE.md (§ Configuration)."
            )

    @property
    def client(self) -> JIRA:
        """Lazy-init the Jira client (only connects when first accessed)."""
        if self._client is None:
            self._client = JIRA(server=self.url, basic_auth=(self.email, self.token))
        return self._client

    # Link types and the retired label come from config.yaml, so no agent -
    # and no query in this adapter - hard-codes a link type name. Read lazily
    # and cached per instance.
    @property
    def _settings(self) -> dict:
        cached = self.__dict__.get("_settings_cache")
        if cached is None:
            cached = tracker_settings()
            self.__dict__["_settings_cache"] = cached
        return cached

    @property
    def link_types(self) -> dict:
        return self._settings["link_types"]

    @property
    def retired_label(self) -> str:
        return self._settings["retired_label"]

    # ─────────────────────────────────────────────────────────────
    # Story selection
    # ─────────────────────────────────────────────────────────────

    # ─────────────────────────────────────────────────────────────
    # Sprint resolution
    # ─────────────────────────────────────────────────────────────

    def get_active_sprint_name(self) -> Optional[str]:
        """Return the name of the currently active sprint on this board.

        Uses jira.sprints(board_id, state="active"). Result is cached for
        the lifetime of this JiraClient instance so Agent 2's three scan
        passes make only one API call.

        Returns None (with a logged warning, never an exception) when:
          - JIRA_BOARD_ID env var is not set
          - the board has no active sprint (sprint not started in Jira)
          - the Jira API call fails
        Callers treat None as "no sprint filter" — degrade gracefully.
        """
        if self._active_sprint_cache is not None:
            return self._active_sprint_cache

        if not self.board_id:
            logger.warning(
                "JIRA_BOARD_ID env var not set — cannot auto-resolve active "
                "sprint. Set JIRA_BOARD_ID (see docs/GUIDE.md § Configuration) or "
                "use an explicit sprint name in config.yaml."
            )
            return None

        try:
            active = self.client.sprints(board_id=int(self.board_id), state="active")
            if not active:
                logger.warning(
                    f"Board {self.board_id}: no active sprint found. "
                    "Has the sprint been started in Jira?"
                )
                return None
            name = active[0].name
            if len(active) > 1:
                logger.warning(
                    f"Board {self.board_id} has {len(active)} active sprints; "
                    f"using the first: {name!r}"
                )
            self._active_sprint_cache = name
            logger.info(f"Auto-resolved active sprint from board {self.board_id}: {name!r}")
            return name
        except Exception as e:
            logger.warning(
                f"Could not fetch active sprint from board {self.board_id}: "
                f"{type(e).__name__}: {e}. Sprint filter will be skipped this run."
            )
            return None

    def get_story(self, issue_key: str) -> dict:
        """Fetch a single story and return its key fields as a dict."""
        issue = self.client.issue(issue_key)
        logger.info(f"Fetched {issue_key}: {issue.fields.summary}")
        # Components drive module-wise app-context selection (backlog 2.1).
        # Absent/empty on most stories — callers must treat [] as "no modules".
        try:
            components = [c.name for c in (issue.fields.components or [])]
        except AttributeError:
            components = []
        return {
            "key": issue.key,
            "summary": issue.fields.summary,
            "description": issue.fields.description or "",
            "status": issue.fields.status.name,
            "labels": list(issue.fields.labels),
            "components": components,
        }

    def find_stories_to_process(
        self,
        selection_config: dict,
        max_results: int = 50,
        sprint_override: str | None = None,
    ) -> list[dict]:
        """
        Find stories matching ALL criteria in selection_config.

        selection_config example:
            {
                "issue_type": "Story",
                "allowed_statuses": ["To Do", "In Progress"],
                "required_labels": ["ai-ready"],
                "excluded_labels": ["ai-processed", "ai-skip"],
                "sprint": "Sprint 10",   # optional — scope to one sprint
            }

        sprint_override: when provided, takes precedence over the "sprint"
            key in selection_config. Used by the --sprint CLI flag so you
            can change the active sprint without editing config.yaml.

        Sprint JQL notes:
            - Accepts the sprint NAME (e.g. "Sprint 10") or numeric sprint ID.
            - Use the special value "openSprints" to always target the currently
              active sprint — useful when you don't want to update config.yaml
              at every sprint boundary.
            - Omitting the key entirely keeps the old behaviour: all sprints.
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

        # Sprint scoping — priority: CLI override > config value > no filter.
        # Special values:
        #   "auto"        → resolve the active sprint from Jira via JIRA_BOARD_ID
        #   "openSprints" → Jira's dynamic JQL alias for the active sprint
        # Anything else is treated as an exact sprint name (or numeric ID).
        # When absent the query spans all sprints (backward-compatible).
        effective_sprint = sprint_override or selection_config.get("sprint")

        if effective_sprint and str(effective_sprint).lower() == "auto":
            resolved = self.get_active_sprint_name()
            if resolved:
                effective_sprint = resolved
                logger.info(f"Sprint 'auto' resolved to: {effective_sprint!r}")
            else:
                logger.warning(
                    "Sprint 'auto' could not resolve the active sprint — "
                    "scanning across all sprints this run."
                )
                effective_sprint = None

        if effective_sprint:
            if str(effective_sprint).lower() == "opensprints":
                jql_parts.append("sprint in openSprints()")
            else:
                jql_parts.append(f'sprint = "{effective_sprint}"')
            logger.info(f"Sprint filter active: {effective_sprint!r}")
        else:
            logger.debug("No sprint filter — scanning across all sprints.")

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
        summary = self._format_test_case_summary(test_case)

        issue_dict = {
            "project": {"key": self.project_key},
            "summary": summary,
            "description": description,
            "issuetype": {"name": "Test Case"},
        }

        new_issue = self.client.create_issue(fields=issue_dict)
        logger.info(f"Created Test Case: {new_issue.key} — {test_case.title}")

        self._link_to_story(new_issue.key, parent_story_key)
        return new_issue

    @staticmethod
    def _format_test_case_summary(tc: TestCase) -> str:
        """`[<test_type>] <title>`, without doubling a prefix the LLM already wrote."""
        prefix = f"[{tc.test_type}]"
        return tc.title if tc.title.startswith(prefix) else f"{prefix} {tc.title}"

    def update_test_case(self, issue_key: str, test_case: TestCase) -> None:
        """Rewrite summary and description with the same formatters as
        `create_test_case`, so the marker hash of the revised scenario is
        computed from exactly what Jira holds. Links and labels untouched."""
        issue = self.client.issue(issue_key)
        issue.update(fields={
            "summary": self._format_test_case_summary(test_case),
            "description": self._format_test_case_description(test_case),
        })
        logger.info(f"Updated Test Case: {issue_key} — {test_case.title}")

    def _link_to_story(self, test_case_key: str, story_key: str) -> None:
        """Create the ownership link (`link_types.owns`) between Test Case and Story.

        Note: failures here are NOT silently swallowed. A missing link means
        Agent 2 won't find the test cases later (it queries by linkedIssues).
        We log at ERROR level and re-raise — the caller can decide whether
        to abort the batch or continue with a partial result.
        """
        from jira.exceptions import JIRAError
        try:
            self._create_link(story_key, test_case_key, "owns")
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
    # Links
    # ─────────────────────────────────────────────────────────────

    def _link_type(self, kind: str) -> dict:
        if kind not in self.link_types:
            raise ValueError(
                f"Unknown link kind {kind!r}; expected one of {sorted(self.link_types)}"
            )
        return self.link_types[kind]

    def _create_link(self, from_key: str, to_key: str, kind: str) -> None:
        """Jira reads a link as `inwardIssue <outward description> outwardIssue`.
        `from_field` in config says which side the `from` issue goes to."""
        lt = self._link_type(kind)
        if lt.get("from_field", "inwardIssue") == "inwardIssue":
            inward, outward = from_key, to_key
        else:
            inward, outward = to_key, from_key
        self.client.create_issue_link(
            type=lt["name"], inwardIssue=inward, outwardIssue=outward,
        )

    def _find_links(self, from_key: str, to_key: str, kind: str) -> list:
        """Links of type `kind` between the two issues, either direction."""
        name = self._link_type(kind)["name"].lower()
        issue = self.client.issue(from_key, fields="issuelinks")
        found = []
        for link in getattr(issue.fields, "issuelinks", []) or []:
            if (getattr(link.type, "name", "") or "").lower() != name:
                continue
            other = getattr(link, "outwardIssue", None) or getattr(link, "inwardIssue", None)
            if other is not None and other.key == to_key:
                found.append(link)
        return found

    def link_issues(self, from_key: str, to_key: str, kind: str) -> None:
        """Create a `kind` link reading `from_key <kind> to_key`. Idempotent."""
        if self._find_links(from_key, to_key, kind):
            logger.info(f"{from_key} already {kind} {to_key} — skipped")
            return
        self._create_link(from_key, to_key, kind)
        logger.info(f"Linked {from_key} {kind} {to_key}")

    def unlink_issues(self, from_key: str, to_key: str, kind: str) -> None:
        """Remove every `kind` link between the two issues. No-op if absent."""
        links = self._find_links(from_key, to_key, kind)
        for link in links:
            self.client.delete_issue_link(link.id)
        if links:
            logger.info(f"Removed {len(links)} '{kind}' link(s) {from_key} — {to_key}")
        else:
            logger.info(f"No '{kind}' link between {from_key} and {to_key} — nothing to remove")

    def create_story(self, summary: str, description: str,
                     components: list[str], labels: list[str]) -> str:
        """Create a Story and return its key (maintenance work with no
        requirement story behind it)."""
        fields = {
            "project": {"key": self.project_key},
            "summary": summary,
            "description": description,
            "issuetype": {"name": "Story"},
            "labels": list(labels or []),
        }
        if components:
            fields["components"] = [{"name": c} for c in components]
        issue = self.client.create_issue(fields=fields)
        logger.info(f"Created Story: {issue.key} — {summary}")
        return issue.key

    # ─────────────────────────────────────────────────────────────
    # Review sub-tasks
    # ─────────────────────────────────────────────────────────────

    def create_subtask(self, parent_key: str, summary: str, description: str) -> str:
        from core.impact_settings import impact_settings
        issue_type = impact_settings()["review"]["issue_type"]
        issue = self.client.create_issue(fields={
            "project": {"key": self.project_key},
            "parent": {"key": parent_key},
            "summary": summary,
            "description": description,
            "issuetype": {"name": issue_type},
        })
        logger.info(f"Created {issue_type} {issue.key} under {parent_key}: {summary}")
        return issue.key

    def get_subtasks(self, parent_key: str) -> list[dict]:
        jql = f'parent = "{parent_key}" ORDER BY created ASC'
        issues = self.client.enhanced_search_issues(
            jql, maxResults=False, fields="summary,status,description")
        return [{"key": i.key, "summary": i.fields.summary,
                 "status": i.fields.status.name,
                 "description": i.fields.description or ""} for i in issues]

    def set_description(self, issue_key: str, description: str,
                        summary: Optional[str] = None) -> None:
        fields = {"description": description}
        if summary is not None:
            fields["summary"] = summary
        self.client.issue(issue_key).update(fields=fields)
        logger.info(f"Updated {'summary and ' if summary is not None else ''}"
                    f"description of {issue_key}")

    def render_test_case(self, test_case: TestCase) -> dict:
        return {"summary": self._format_test_case_summary(test_case),
                "description": self._format_test_case_description(test_case)}

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

    def get_comments(self, issue_key: str) -> list:
        """Return the body text of every comment on an issue (oldest first).

        Used by the usage ledger (Agent 5) to aggregate [LLM-USAGE] entries
        posted by earlier agents. Returns [] on any failure — reading the
        ledger is best-effort.
        """
        try:
            issue = self.client.issue(issue_key, fields="comment")
            comments = getattr(issue.fields, "comment", None)
            if comments is None:
                return []
            return [getattr(c, "body", "") or "" for c in comments.comments]
        except Exception as e:
            logger.warning(f"Could not fetch comments for {issue_key}: {e}")
            return []

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

    def transition_status(self, issue_key: str, status: str) -> bool:
        """Move an issue to a named status (board column). True if it moved.

        Jira exposes moves as *transitions*, not direct status writes, and the
        available transitions depend on the workflow and the issue's current
        state. We look up the transition whose target matches `status`.

        Never raises: a missing status, a workflow that forbids the move, or a
        permissions problem all return False. Board position is cosmetic - it
        must not fail a pipeline run that has already done real work.
        """
        try:
            issue = self.client.issue(issue_key, fields="status")
            current = getattr(issue.fields.status, "name", "")
            if current.strip().lower() == status.strip().lower():
                return True                       # already there
            for t in self.client.transitions(issue):
                target = (t.get("to") or {}).get("name", "")
                if target.strip().lower() == status.strip().lower():
                    self.client.transition_issue(issue, t["id"])
                    logger.info(f"{issue_key}: '{current}' -> '{target}'")
                    return True
            available = [(t.get("to") or {}).get("name") for t in self.client.transitions(issue)]
            logger.warning(
                f"{issue_key}: no transition to {status!r} from {current!r}. "
                f"Available: {available}. Leaving the card where it is."
            )
        except Exception as e:
            logger.warning(f"{issue_key}: could not transition to {status!r}: {e}")
        return False

    def _test_case_jql(self, story_key: str, kind: str) -> str:
        """Test cases linked to `story_key` by link kind, retired ones left out.

        `labels != X` in Jira skips issues with NO labels at all, so the
        `labels is EMPTY` half is what keeps unlabelled test cases in.
        """
        query = self._link_type(kind)["query"]
        return (f'project = {self.project_key} AND issuetype = "Test Case" '
                f'AND issue in linkedIssues("{story_key}", "{query}") '
                f'AND (labels is EMPTY OR labels != "{self.retired_label}")')

    def _search_test_cases(self, jql: str) -> list[dict]:
        issues = self.client.enhanced_search_issues(jql, maxResults=100)
        return [
            {"key": i.key,
             "summary": i.fields.summary,
             "description": i.fields.description or ""}
            for i in issues
        ]

    def get_linked_test_cases(self, story_key: str) -> list[dict]:
        """Test Cases this story OWNS, as plain dicts.

        Returns [{"key", "summary", "description"}, ...]. Only the ownership
        link counts: a test case this story merely impacts belongs to another
        story and is returned by `get_impacted_test_cases` instead.

        The JQL lives HERE, not in the agents: JQL is Jira-only, so a caller
        that builds its own query cannot be pointed at Xray, TestRail or Azure
        DevOps without editing the agent. Every tracker-specific detail belongs
        behind this adapter.
        """
        jql = self._test_case_jql(story_key, "owns")
        logger.info(f"Fetching test cases owned by {story_key}: {jql}")
        test_cases = self._search_test_cases(jql)
        logger.info(f"Found {len(test_cases)} test cases owned by {story_key}")
        return test_cases

    def get_impacted_test_cases(self, story_key: str,
                                include_retired: bool = False) -> list[dict]:
        """Test Cases this story IMPACTS (owned by other stories).

        With include_retired, retired ones are returned too and every dict
        carries "retired": bool.
        """
        if not include_retired:
            jql = self._test_case_jql(story_key, "impacts")
            logger.info(f"Fetching test cases impacted by {story_key}: {jql}")
            test_cases = self._search_test_cases(jql)
            logger.info(f"Found {len(test_cases)} test cases impacted by {story_key}")
            return test_cases
        query = self._link_type("impacts")["query"]
        jql = (f'project = {self.project_key} AND issuetype = "Test Case" '
               f'AND issue in linkedIssues("{story_key}", "{query}")')
        issues = self.client.enhanced_search_issues(
            jql, maxResults=100, fields="summary,description,labels")
        return [{"key": i.key, "summary": i.fields.summary,
                 "description": i.fields.description or "",
                 "retired": self.retired_label in (getattr(i.fields, "labels", None) or [])}
                for i in issues]

    def get_impacting_stories(self, test_case_key: str) -> list[str]:
        inverse = self._link_type("impacts")["inverse_query"]
        jql = (f'project = {self.project_key} AND issuetype = "Story" '
               f'AND issue in linkedIssues("{test_case_key}", "{inverse}") ORDER BY key ASC')
        try:
            return [i.key for i in self.client.enhanced_search_issues(
                jql, maxResults=100, fields="summary")]
        except Exception as e:
            logger.warning(f"Could not find stories impacting {test_case_key}: {e}")
            return []

    def count_linked_test_cases(self, story_key: str) -> int:
        """How many Test Case issues this story already OWNS.

        Agent 1 creates Test Cases in a LOOP and only adds `ai-processed`
        afterwards, so a crash mid-loop leaves cases created but the story
        unmarked - and the next run would create the whole set AGAIN. The same
        hole makes `--story` unsafe to run twice by hand.

        Existing owned Test Cases are the evidence that work already happened.
        Impacted ones are not: a change story that revises other stories'
        tests has done none of its own work yet.
        Returns 0 on any lookup failure so a Jira hiccup never blocks a run.
        """
        try:
            jql = self._test_case_jql(story_key, "owns")
            return len(self.client.enhanced_search_issues(jql, maxResults=100))
        except Exception as e:
            logger.warning(f"Could not count test cases for {story_key}: {e}")
            return 0

    def _owner_from_links(self, issuelinks) -> Optional[str]:
        """The owning Story among a test case's issue links, or None.

        Only the OWNERSHIP link names the owner. A test case can also carry
        `impacts` links from stories that revised it; following one of those
        would post the owner's report on the change story instead.

        create_test_case() puts the story on `outwardIssue`, so that side is
        checked first; an ownership link a person added from the story's side
        puts it on `inwardIssue`, which is checked second.
        """
        owns_name = self.link_types["owns"]["name"].lower()
        links = [l for l in issuelinks
                 if (getattr(l.type, "name", "") or "").lower() == owns_name]
        for side in ("outwardIssue", "inwardIssue"):
            for link in links:
                other = getattr(link, side, None)
                if other is None:
                    continue
                other_type = getattr(other.fields.issuetype, "name", "") or ""
                if other_type.lower() == "story":
                    return other.key
        return None

    def get_all_test_cases(self) -> list[dict]:
        """Every non-retired Test Case in the project, with its owner.

        Returns [{"key", "summary", "description", "owner"}, ...]; `owner` is
        the owning story's key, or None. Fetches every page of results.
        """
        jql = (f'project = {self.project_key} AND issuetype = "Test Case" '
               f'AND (labels is EMPTY OR labels != "{self.retired_label}") '
               f'ORDER BY key ASC')
        issues = self.client.enhanced_search_issues(
            jql, maxResults=False, fields="summary,description,issuelinks")
        out = [
            {"key": i.key,
             "summary": i.fields.summary,
             "description": i.fields.description or "",
             "owner": self._owner_from_links(getattr(i.fields, "issuelinks", []) or [])}
            for i in issues
        ]
        logger.info(f"Found {len(out)} test cases in project {self.project_key}")
        return out

    def get_parent_story_key(self, issue_key: str) -> Optional[str]:
        """Return the parent Story key for a Test Case, or None if not applicable.

        Used by Agent 5 (Reporter) to ensure run-summary comments land on the
        user-facing Story (e.g. SCRUM-20) instead of the implementation-detail
        Test Case (e.g. SCRUM-23) extracted from a feature branch name.

        Resolution logic:
          - If `issue_key` itself is a Story (or anything that's not a Test Case),
            return None — caller should keep the original key.
          - If `issue_key` is a Test Case, scan its issuelinks for the ownership
            link (`link_types.owns`) to a Story and return that Story's key.
            Links of any other type - `impacts` above all - are ignored.
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

        owner = self._owner_from_links(getattr(issue.fields, "issuelinks", []) or [])
        if owner:
            logger.info(f"Resolved test-case {issue_key} → parent story {owner}")
            return owner

        logger.info(
            f"{issue_key} is a Test Case but has no ownership link to a Story; "
            f"will comment on {issue_key} itself."
        )
        return None