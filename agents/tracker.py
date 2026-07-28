"""Tracker abstraction — the pipeline's contract with an issue tracker.

WHY THIS EXISTS
---------------
The agents need exactly ten operations from a tracker: read a story, find work,
create a test case, read the test cases linked to a story, and move state
markers (labels/comments) around. Nothing more.

Every one of those exists in Jira, Xray, TestRail, Azure DevOps and Linear —
under different names, with different query languages. Depending on
`JiraClient` directly meant a different client's deployment needed edits in
five agent files. Depending on this Protocol means it needs one new adapter.

WHAT BELONGS BEHIND AN ADAPTER
------------------------------
Anything tracker-shaped: JQL and other query languages, issue types, link
types, field names, pagination, auth. If an agent can name it, the abstraction
has leaked.

WHAT THE AGENTS MAY ASSUME
--------------------------
Only what is in `Tracker` below, and that stories/test cases come back as plain
dicts with the keys documented on each method. No tracker objects escape the
adapter.

ADDING A TRACKER
----------------
1. Write a class implementing `Tracker` (no inheritance needed — this is a
   structural Protocol, so a class matching the shape simply *is* a Tracker).
2. Register it in `_ADAPTERS` below.
3. Set `tracker.type` in config.yaml.

Nothing in agents/ changes.

A NOTE ON LABELS
----------------
The pipeline's state machine is labels (`ai-ready` -> `ai-processed` -> ...).
Jira has them natively. A tracker without labels (TestRail) should implement
`add_label`/`remove_label`/`get_labels` over whatever it does have — a custom
field, a tag list, a status. The agents only require that a marker can be set,
cleared and read back; they never assume it is literally a Jira label.
"""
from __future__ import annotations

import logging
from typing import Any, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class Tracker(Protocol):
    """The complete set of tracker operations the pipeline uses."""

    # ── identity ─────────────────────────────────────────────
    @property
    def project_key(self) -> str:
        """Project/board identifier, used in branch names and logs."""
        ...

    # ── reading work ─────────────────────────────────────────
    def get_story(self, key: str) -> dict:
        """One story as {"key", "summary", "description", "labels", ...}."""
        ...

    def find_stories_to_process(self, selection: dict,
                                sprint_override: Optional[str] = None) -> list[dict]:
        """Stories matching a selection rule from config.yaml.

        `selection` carries issue_type / required_labels / excluded_labels /
        allowed_statuses / sprint. Translating that into a query is the
        adapter's job — the agents never build one.
        """
        ...

    def get_parent_story_key(self, key: str) -> Optional[str]:
        """Parent story of a test case, or None if `key` is already a story."""
        ...

    # ── test cases ───────────────────────────────────────────
    def create_test_case(self, story_key: str, test_case: Any) -> Any:
        """Create a test case and link it to the story. Returns the new issue."""
        ...

    def get_linked_test_cases(self, story_key: str) -> list[dict]:
        """Linked test cases as [{"key", "summary", "description"}, ...]."""
        ...

    def count_linked_test_cases(self, story_key: str) -> int:
        """How many test cases are linked. Must return 0 on lookup failure so a
        tracker outage never blocks the pipeline."""
        ...

    # ── state markers ────────────────────────────────────────
    def add_label(self, key: str, label: str) -> None: ...
    def remove_label(self, key: str, label: str) -> None: ...

    # ── audit trail ──────────────────────────────────────────
    def add_comment(self, key: str, body: str) -> None: ...
    def get_comments(self, key: str) -> list[str]: ...


# ─────────────────────────────────────────────────────────────
# Factory
# ─────────────────────────────────────────────────────────────

def _jira_adapter():
    from agents.jira_client import JiraClient
    return JiraClient()


# name -> zero-arg callable returning a Tracker. Imports are deferred so an
# unused adapter's dependency never has to be installed.
_ADAPTERS: dict[str, Any] = {
    "jira": _jira_adapter,
}

_cached: dict[str, Tracker] = {}


def get_tracker(tracker_type: Optional[str] = None, *, fresh: bool = False) -> Tracker:
    """Return the configured tracker.

    Reads `tracker.type` from config.yaml, defaulting to "jira" so existing
    deployments keep working with no config change.

    Instances are cached per type: agents call this in several places and each
    adapter may hold a connection. Pass `fresh=True` to bypass the cache (used
    by tests).
    """
    if tracker_type is None:
        tracker_type = _configured_type()
    tracker_type = tracker_type.strip().lower()

    if not fresh and tracker_type in _cached:
        return _cached[tracker_type]

    if tracker_type not in _ADAPTERS:
        raise ValueError(
            f"Unknown tracker type {tracker_type!r}. "
            f"Available: {', '.join(sorted(_ADAPTERS))}. "
            f"Add an adapter to agents/tracker.py to support a new tool."
        )

    instance = _ADAPTERS[tracker_type]()
    if not fresh:
        _cached[tracker_type] = instance
    logger.debug(f"Tracker adapter: {tracker_type}")
    return instance


def _configured_type() -> str:
    """`tracker.type` from config.yaml, or "jira"."""
    try:
        import yaml
        from config.paths import CONFIG_YAML
        data = yaml.safe_load(CONFIG_YAML.read_text(encoding="utf-8")) or {}
        return (data.get("tracker") or {}).get("type", "jira")
    except Exception:                      # missing/rewritten config -> default
        return "jira"


def register_adapter(name: str, factory) -> None:
    """Register a tracker adapter at runtime.

    For a client shipping their own adapter without editing this file.
    """
    _ADAPTERS[name.strip().lower()] = factory