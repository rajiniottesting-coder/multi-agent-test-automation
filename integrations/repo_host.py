"""Repo-host abstraction — the pipeline's contract with a code-hosting platform.

WHY THIS EXISTS
---------------
Agents 2, 3 and 5 plus the sweeper need a fixed set of operations from wherever
the code lives: create a branch, commit files, open a PR, read a PR's metadata
and changed files, comment on it, and ask whether CI has settled. All of that
exists in GitHub, GitLab, Azure Repos and Bitbucket under different names.

Depending on `GitHubClient` directly meant a client on GitLab needed edits in
three agents and the sweeper. Depending on this Protocol means one new adapter.

SIGNATURES ARE THE CONTRACT
---------------------------
These were derived from the REAL call sites, not from what the API ought to
look like. `tests/unit/test_repo_host_abstraction.py` compares this Protocol
against every adapter parameter-by-parameter and fails the build on drift.

PLAIN DICTS ONLY — AND THE KEYS ARE PART OF THE CONTRACT
--------------------------------------------------------
No method returns a provider object. `find_open_pr_for_story` used to hand back
a PyGithub PR and agents read `.number` / `.head.ref` off it — which would have
forced a GitLab adapter to impersonate PyGithub's object shape. Every PR is
now {"number", "head_ref", "head_sha", "url", "title"}.

Every dict-returning method documents its exact keys below. A missing key is a
KeyError in an agent, not a graceful degradation, so an adapter must supply all
of them. `test_repo_host_abstraction.py` asserts the documented keys against a
sample adapter.

WHAT DOES NOT BELONG HERE
-------------------------
The `pull_request` EVENT that triggers Agents 3/4/5 is a workflow-level concern
(.github/workflows/*.yml), not an API call. A GitLab deployment replaces those
workflow files with `.gitlab-ci.yml`; this Protocol covers the API surface the
Python code uses, not the CI wiring.

ADDING A HOST
-------------
1. Write a class implementing `RepoHost` (structural Protocol — no inheritance).
2. `register_adapter("gitlab", GitLabHost)`.
3. Set `repo_host.type` in config.yaml.
4. Replace the credential env vars in the three workflows that talk to the
   repo host: agent2_coder, agent3-reviewer and sweeper.

Nothing in agents/ changes — but note that step 4 is the *cheap* case, and it
only applies if CI stays on GitHub Actions. Moving the code to another host
normally moves CI too, and all six workflow files use GitHub Actions-specific
constructs (actions/checkout, actions/setup-python, github.event.*). Those are
rewritten, not edited. See "WHAT DOES NOT BELONG HERE" above.

One further obligation on a new adapter, not enforced by this Protocol:
`get_workflow_runs()` returns {"status", "conclusion", "head_sha"} — the KEYS
are contractual but the VALUES are not. scripts/sweep_stalled_prs.py compares
them against GitHub Actions vocabulary (_SETTLED_CONCLUSIONS, _ACTIVE_STATUSES).
A non-GitHub adapter must map its own statuses onto those strings, or the
sweeper will treat every pipeline as unsettled and re-trigger it forever.
"""
from __future__ import annotations

import logging
from typing import Any, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class RepoHost(Protocol):
    """Every repo-host operation the pipeline uses."""

    # ── branches ─────────────────────────────────────────────
    def create_branch(self, branch_name: str, from_branch: str = "main") -> None:
        """Create a branch. Idempotent: an existing branch is reused, not an error."""
        ...

    def branch_exists(self, branch_name: str) -> bool: ...

    def delete_branch(self, branch_name: str) -> bool:
        """Delete a branch. True if deleted. Used to discard a partially-written
        branch when no PR exists, so a crashed run cannot leave stale files."""
        ...

    # ── files ────────────────────────────────────────────────
    def create_or_update_file(self, path: str, content: str,
                              commit_message: str, branch: str) -> None: ...

    def get_file_content(self, path: str, branch: str = "main") -> str: ...

    def list_files_in_directory(self, path: str, branch: str = "main") -> list[str]: ...

    # ── pull requests ────────────────────────────────────────
    def open_pull_request(self, title: str, body: str, head_branch: str,
                          base_branch: str = "main") -> str:
        """Open a PR. Returns its URL."""
        ...

    def find_open_pr_for_story(self, story_id: str,
                               branch_prefix: str = "auto/") -> Optional[dict]:
        """Open PR for a story as {"number","head_ref","head_sha","url","title"}."""
        ...

    def list_open_prs(self, branch_prefix: str = "") -> list[dict]:
        """All open PRs as dicts, optionally filtered by branch prefix."""
        ...

    def find_prs_for_story(self, story_id: str, branch_prefix: str = "auto/") -> list[dict]:
        """EVERY PR of a story - open, closed and merged - newest first, as
        [{"number", "head_ref", "url", "title", "state", "merged", "updated_at"}].
        `state` is "open" or "closed"; `merged` tells a merge from a rejection
        (get_pr_metadata has no such flag). `updated_at` is ISO-8601 text.
        Used by the reconcile scan (Agent 0, C7)."""
        ...

    def get_pr_metadata(self, pr_number: int) -> dict:
        """Full PR detail. MUST return exactly these keys:

            {"number", "title", "body", "head_branch", "base_branch",
             "state", "author", "url"}

        NOTE the key is `head_branch` here, but `head_ref` in
        find_open_pr_for_story / list_open_prs. They mean the same thing; the
        names differ for historical reasons and agent3_reviewer reads
        `head_branch`. An adapter must supply BOTH spellings in their
        respective methods or those callers raise KeyError.
        """
        ...

    def get_pr_changed_files(self, pr_number: int) -> list[dict]:
        """Changed files as [{"filename", "status", "additions", "deletions",
        "patch"}, ...]. `patch` is the unified diff and may be empty for
        binary or very large files."""
        ...

    def reopen_pull_request(self, pr_number: int) -> None:
        """Close then reopen, to re-fire event-driven CI. Provider-specific:
        GitLab would retry a pipeline instead."""
        ...

    # ── comments ─────────────────────────────────────────────
    def post_pr_comment(self, pr_number: int, body: str) -> None: ...

    def get_pr_comments(self, pr_number: int) -> list[str]: ...

    # ── CI status ────────────────────────────────────────────
    def get_workflow_runs(self, workflow_file: str, branch: str,
                          limit: int = 20) -> list[dict]:
        """Recent CI runs as [{"status","conclusion","head_sha"}, ...].

        "Workflow" is GitHub's word; a GitLab adapter maps this onto pipelines
        and an Azure adapter onto builds.
        """
        ...


# ─────────────────────────────────────────────────────────────
# Factory
# ─────────────────────────────────────────────────────────────

def _github_adapter():
    from integrations.github_client import GitHubClient
    return GitHubClient()


_ADAPTERS: dict[str, Any] = {
    "github": _github_adapter,
}

_cached: dict[str, RepoHost] = {}


def get_repo_host(host_type: Optional[str] = None, *, fresh: bool = False) -> RepoHost:
    """Return the configured repo host.

    Reads `repo_host.type` from config.yaml, defaulting to "github" so existing
    deployments keep working with no config change.
    """
    if host_type is None:
        host_type = _configured_type()
    host_type = host_type.strip().lower()

    if not fresh and host_type in _cached:
        return _cached[host_type]

    if host_type not in _ADAPTERS:
        raise ValueError(
            f"Unknown repo host {host_type!r}. "
            f"Available: {', '.join(sorted(_ADAPTERS))}. "
            f"Add an adapter to integrations/repo_host.py to support a new platform."
        )

    instance = _ADAPTERS[host_type]()
    if not fresh:
        _cached[host_type] = instance
    logger.debug(f"Repo-host adapter: {host_type}")
    return instance


def _configured_type() -> str:
    """`repo_host.type` from config.yaml, or "github"."""
    try:
        import yaml
        from config.paths import CONFIG_YAML
        data = yaml.safe_load(CONFIG_YAML.read_text(encoding="utf-8")) or {}
        return (data.get("repo_host") or {}).get("type", "github")
    except Exception:
        return "github"


def register_adapter(name: str, factory) -> None:
    """Register a repo-host adapter at runtime, for a client shipping their own."""
    _ADAPTERS[name.strip().lower()] = factory

def registered_types() -> list[str]:
    """Names of the repo-host adapters that can be constructed by name (E2)."""
    return sorted(_ADAPTERS)
