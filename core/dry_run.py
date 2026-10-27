"""Dry run: run the real code against the real tracker and repo host, but
perform none of their writes.

A dry run that re-implements "what would happen" drifts from what does
happen. This wraps the adapters instead: every READ passes through, every
other operation is recorded and NOT sent, so the exact code path of a live
run produces the list of writes it would have made.

Fail-safe by construction: an operation is let through only when it is
listed in TRACKER_READS / REPO_HOST_READS. An operation added to a Protocol
later is therefore intercepted until someone decides it is a read, and
tests/unit/test_dry_run.py fails until every Protocol member is classified.
Writes return None; the callers that use a dry run (reconcile, the Agent 0
hand-over) ignore the return values of writes.
"""
from __future__ import annotations

from typing import Any

TRACKER_READS = frozenset({
    "project_key", "get_story", "find_stories_to_process", "get_parent_story_key",
    "get_linked_test_cases", "count_linked_test_cases", "get_all_test_cases",
    "get_impacted_test_cases", "get_impacting_stories", "get_subtasks",
    "render_test_case", "get_comments",
})
# Optional capabilities (integrations.tracker, OPTIONAL CAPABILITIES) that only
# read. Not Protocol members, so kept apart from the classified sets above; every
# other capability (set_property, update_comment, ...) is a write and recorded.
CAPABILITY_READS = frozenset({
    "get_property", "property_keys", "properties", "render_markdown", "check_access",
})
TRACKER_WRITES = frozenset({
    "create_test_case", "update_test_case", "link_issues", "unlink_issues",
    "create_story", "create_subtask", "set_description", "add_label",
    "remove_label", "transition_status", "add_comment",
})

REPO_HOST_READS = frozenset({
    "branch_exists", "get_file_content", "list_files_in_directory",
    "find_open_pr_for_story", "list_open_prs", "find_prs_for_story",
    "get_pr_metadata", "get_pr_changed_files", "get_pr_comments", "get_workflow_runs",
    "get_run_artifact_file", "get_review_comments",
})
REPO_HOST_WRITES = frozenset({
    "create_branch", "delete_branch", "create_or_update_file", "open_pull_request",
    "reopen_pull_request", "close_pull_request", "post_pr_comment",
    "reply_to_review_comment",
})


class DryRun:
    """Wrap an adapter: reads pass through, everything else is recorded."""

    def __init__(self, inner: Any, reads: frozenset, label: str = ""):
        self._inner = inner
        self._reads = reads
        self._label = label or type(inner).__name__
        self.writes: list[tuple[str, tuple, dict]] = []

    def __getattr__(self, name: str):
        if name in self._reads:
            return getattr(self._inner, name)
        attr = getattr(self._inner, name)
        if not callable(attr):
            return attr

        def record(*args, **kwargs):
            self.writes.append((name, args, kwargs))
        return record

    def describe(self) -> list[str]:
        """One line per write that was NOT performed."""
        out = []
        for name, args, kwargs in self.writes:
            shown = [_short(a) for a in args] + [f"{k}={_short(v)}" for k, v in kwargs.items()]
            out.append(f"[dry run] {self._label}.{name}({', '.join(shown)})")
        return out


def tracker(inner: Any) -> DryRun:
    return DryRun(inner, TRACKER_READS | CAPABILITY_READS, "tracker")


def repo_host(inner: Any) -> DryRun:
    return DryRun(inner, REPO_HOST_READS, "repo_host")


def _short(value: Any, limit: int = 80) -> str:
    text = repr(value)
    return text if len(text) <= limit else text[:limit] + "..."
