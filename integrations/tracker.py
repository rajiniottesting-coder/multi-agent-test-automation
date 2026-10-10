"""Tracker abstraction — the pipeline's contract with an issue tracker.

WHY THIS EXISTS
---------------
The agents need sixteen operations from a tracker: read a story, find work,
create and update a test case, read the test cases a story owns and the ones
it impacts, list every test case, link and unlink issues, create a story, and
move state markers (labels/comments) around. Nothing more.

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
4. Replace the credential env vars in the five workflows that talk to the
   tracker: agent1_analyst, agent2_coder, agent3-reviewer, agent4_runner and
   story_done_on_merge. Each passes the adapter's variables through an `env:`
   block, so a new adapter reading different names needs them supplied.
   (sweeper.yml is the one workflow that never touches the tracker.)

Nothing in agents/ changes. Steps 1-3 are the Python contract; step 4 is the
credential plumbing, which the Protocol deliberately does not cover.

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
    """The complete set of tracker operations the pipeline uses.

    SIGNATURES ARE THE CONTRACT, not just the names. These were derived from
    the real call sites in agents/ - a new adapter must match them exactly,
    parameter names included, because some call sites use keyword arguments.
    `tests/unit/test_tracker_abstraction.py` compares this Protocol against
    every registered adapter and fails the build on any drift.
    """

    # ── identity ─────────────────────────────────────────────
    @property
    def project_key(self) -> str:
        """Project/board identifier, used in branch names and logs."""
        ...

    # ── reading work ─────────────────────────────────────────
    def get_story(self, issue_key: str) -> dict:
        """One story as {"key", "summary", "description", "labels", "components"}."""
        ...

    def find_stories_to_process(self, selection_config: dict,
                                max_results: int = 5,
                                sprint_override: Optional[str] = None) -> list[dict]:
        """Stories matching a selection rule from config.yaml.

        `selection_config` carries issue_type / required_labels /
        excluded_labels / allowed_statuses / sprint. Translating that into a
        query is the adapter's job - the agents never build one.
        """
        ...

    def get_parent_story_key(self, issue_key: str) -> Optional[str]:
        """Parent story of a test case, or None if `issue_key` is a story."""
        ...

    # ── test cases ───────────────────────────────────────────
    def create_test_case(self, test_case: Any, parent_story_key: str) -> Any:
        """Create a test case and link it to the parent story.

        NOTE the argument ORDER: test_case first. agent1_analyst calls this as
        `create_test_case(tc, parent_story_key=story_id)` - a keyword - so both
        the order AND the name `parent_story_key` are part of the contract.
        """
        ...

    def get_linked_test_cases(self, story_key: str) -> list[dict]:
        """The test cases this story OWNS, as [{"key", "summary", "description"}, ...].

        Only the ownership link counts (`link_types.owns`), and retired test
        cases (`retired_label`) are left out. A test case another story merely
        impacts is not returned here - see `get_impacted_test_cases`.
        """
        ...

    def count_linked_test_cases(self, story_key: str) -> int:
        """How many test cases this story owns (same filter as
        `get_linked_test_cases`). Must return 0 on lookup failure so a
        tracker outage never blocks the pipeline."""
        ...

    def get_all_test_cases(self) -> list[dict]:
        """Every non-retired test case in the project, as
        [{"key", "summary", "description", "owner"}, ...] where `owner` is the
        owning story's key or None. Used by the marker backfill and by
        Agent 0's whole-suite analysis."""
        ...

    def get_impacted_test_cases(self, story_key: str) -> list[dict]:
        """The test cases this story IMPACTS - owned by other stories, revised
        by this one (`link_types.impacts`). Same dict shape as
        `get_linked_test_cases`; retired test cases are left out."""
        ...

    def update_test_case(self, issue_key: str, test_case: Any) -> None:
        """Rewrite an existing test case's summary and description, formatted
        exactly as `create_test_case` formats them, so the scenario marker's
        hash stays comparable. Links and labels are untouched."""
        ...

    # ── links ────────────────────────────────────────────────
    def link_issues(self, from_key: str, to_key: str, kind: str) -> None:
        """Create a link reading `from_key <kind> to_key`.

        `kind` is a pipeline concept, never a tracker link name:
          "owns"    - story `from_key` owns test case `to_key`
          "impacts" - story `from_key` changed `to_key` (a test case, or the
                      story that owns it)
        The adapter maps the kind to its configured link type and direction.
        Idempotent: an existing identical link is left alone.
        """
        ...

    def unlink_issues(self, from_key: str, to_key: str, kind: str) -> None:
        """Remove the `kind` link between the two issues. No-op if absent."""
        ...

    def create_story(self, summary: str, description: str,
                     components: list[str], labels: list[str]) -> str:
        """Create a story and return its key. Used for maintenance work that
        no requirement story stands behind."""
        ...

    # ── state markers ────────────────────────────────────────
    def add_label(self, issue_key: str, label: str) -> None: ...
    def remove_label(self, issue_key: str, label: str) -> None: ...

    # ── board position ───────────────────────────────────────
    def transition_status(self, issue_key: str, status: str) -> bool:
        """Move an issue to `status` (a board column). True if it moved.

        Board columns are STATUSES, not labels - a label marks pipeline state,
        a status is where the card sits. Both matter: labels drive the agents,
        statuses tell a human at a glance what is happening.

        MUST return False rather than raise when the status does not exist or
        the transition is not permitted. Board hygiene is cosmetic; it must
        never fail a pipeline run. Adapters for trackers without a workflow
        (a flat task list) may return False always.
        """
        ...

    # ── audit trail ──────────────────────────────────────────
    def add_comment(self, issue_key: str, body: str) -> str:
        """Post a comment. Returns a URL/identifier for it where available."""
        ...

    def get_comments(self, issue_key: str) -> list:
        """All comment bodies on the issue."""
        ...


# ─────────────────────────────────────────────────────────────
# Factory
# ─────────────────────────────────────────────────────────────

def _jira_adapter():
    from integrations.jira_client import JiraClient
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


# ─────────────────────────────────────────────────────────────
# Link and label settings shared by every adapter
# ─────────────────────────────────────────────────────────────

LINK_KINDS = ("owns", "impacts")

# Used when config.yaml has no `tracker.link_types` block, so an existing
# deployment keeps today's behaviour: every test case is owned through the
# link type it has always been created with.
_DEFAULT_LINK_TYPES: dict[str, dict] = {
    "owns": {"name": "Relates", "query": "relates to",
             "inverse_query": "relates to", "from_field": "outwardIssue"},
    "impacts": {"name": "Impacts", "query": "impacts",
                "inverse_query": "is impacted by", "from_field": "inwardIssue"},
}
_DEFAULT_RETIRED_LABEL = "ai-retired"


def tracker_settings() -> dict:
    """`tracker.link_types` and `tracker.retired_label` from config.yaml,
    merged over the defaults above. Never raises.

    Returns {"link_types": {kind: {...}}, "retired_label": str}.
    """
    raw: dict = {}
    try:
        import yaml
        from config.paths import CONFIG_YAML
        data = yaml.safe_load(CONFIG_YAML.read_text(encoding="utf-8")) or {}
        raw = data.get("tracker") or {}
    except Exception:                      # missing/rewritten config -> defaults
        raw = {}
    configured = raw.get("link_types") or {}
    link_types = {}
    for kind in LINK_KINDS:
        merged = dict(_DEFAULT_LINK_TYPES[kind])
        merged.update(configured.get(kind) or {})
        link_types[kind] = merged
    return {
        "link_types": link_types,
        "retired_label": raw.get("retired_label") or _DEFAULT_RETIRED_LABEL,
    }


def register_adapter(name: str, factory) -> None:
    """Register a tracker adapter at runtime.

    For a client shipping their own adapter without editing this file.
    """
    _ADAPTERS[name.strip().lower()] = factory