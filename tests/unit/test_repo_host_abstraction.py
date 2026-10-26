"""The pipeline must depend on the RepoHost Protocol, not on GitHub.

A client on GitLab / Azure Repos / Bitbucket should write one adapter and change
one config line - never edit agents/. These tests pin that, including the two
failure modes that bit the tracker refactor:

  1. name-only conformance (signatures must match too)
  2. provider objects leaking through return values
"""
import inspect
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from integrations.repo_host import RepoHost, get_repo_host, register_adapter

ROOT = Path(__file__).resolve().parents[2]
CALLERS = sorted((ROOT / "agents").glob("agent*.py")) + [
    ROOT / "scripts" / "sweep_stalled_prs.py"]


def _params(func):
    return [p for p in inspect.signature(func).parameters if p != "self"]


# ── the contract ─────────────────────────────────────────────

def test_protocol_covers_every_operation_the_callers_use():
    used = set()
    for f in CALLERS:
        used |= set(re.findall(r"\b(?:gh|host)\.([a-z_]+)\(", f.read_text(encoding="utf-8")))
    declared = {m for m in dir(RepoHost) if not m.startswith("_")}
    missing = used - declared
    assert not missing, f"callers use these, but RepoHost does not declare them: {missing}"


def test_github_adapter_matches_the_protocol_signature_exactly():
    """Name-only conformance is not enough - parameter names and order are
    part of the contract wherever a caller uses keyword arguments."""
    from integrations.github_client import GitHubClient
    mismatches = []
    for member in (m for m in dir(RepoHost) if not m.startswith("_")):
        proto = getattr(RepoHost, member, None)
        impl = getattr(GitHubClient, member, None)
        assert impl is not None, f"GitHubClient is missing {member}"
        if not (callable(proto) and callable(impl)):
            continue
        if _params(proto) != _params(impl):
            mismatches.append(f"{member}: {_params(proto)} != {_params(impl)}")
    assert not mismatches, "GitHubClient drifts from RepoHost:\n  " + "\n  ".join(mismatches)


# ── no provider objects, no provider APIs ────────────────────

def test_callers_never_touch_pygithub():
    """A raw PyGithub call cannot be pointed at GitLab."""
    offenders = []
    for f in CALLERS:
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("#"):
                continue
            if re.search(r"\.repo\.|from github import|\bPyGithub\b|pr\.edit\(", line):
                offenders.append(f"{f.name}: {line.strip()[:70]}")
    assert not offenders, "PyGithub leaked into callers:\n" + "\n".join(offenders)


def test_callers_never_instantiate_a_concrete_host():
    offenders = [f.name for f in CALLERS if "GitHubClient()" in f.read_text(encoding="utf-8")]
    assert not offenders, f"these bypass the factory: {offenders}"


def test_pr_lookups_return_plain_dicts_not_provider_objects():
    """The regression that made a GitLab adapter impossible: agents read
    `.number` / `.head.ref` off a PyGithub PR."""
    from integrations.github_client import GitHubClient
    src = (ROOT / "agents" / "agent2_coder.py").read_text(encoding="utf-8")
    assert "existing_pr.number" not in src
    assert "existing_pr.head" not in src
    assert 'existing_pr["number"]' in src

    pr = MagicMock()
    pr.head.ref, pr.head.sha, pr.number = "auto/S-1-x", "abc123", 7
    pr.html_url, pr.title = "u", "t"
    gh = GitHubClient.__new__(GitHubClient)
    repo = MagicMock(); repo.get_pulls.return_value = [pr]
    with patch.object(GitHubClient, "repo", new_callable=lambda: property(lambda s: repo)):
        out = gh.find_open_pr_for_story("S-1")
    assert isinstance(out, dict)
    assert set(out) == {"number", "head_ref", "head_sha", "url", "title"}


# ── the factory ──────────────────────────────────────────────

def test_unknown_host_names_the_available_ones():
    with pytest.raises(ValueError, match="Unknown repo host"):
        get_repo_host("bitbucket", fresh=True)


def test_a_new_host_needs_no_caller_changes():
    class GitLabLikeHost:
        def __init__(self): self.branches, self.prs, self.comments = set(), {}, {}
        def create_branch(self, branch_name, from_branch="main"): self.branches.add(branch_name)
        def branch_exists(self, branch_name): return branch_name in self.branches
        def delete_branch(self, branch_name):
            self.branches.discard(branch_name); return True
        def create_or_update_file(self, path, content, commit_message, branch): pass
        def get_file_content(self, path, branch="main"): return ""
        def list_files_in_directory(self, path, branch="main"): return []
        def open_pull_request(self, title, body, head_branch, base_branch="main"):
            n = len(self.prs) + 1
            self.prs[n] = {"number": n, "head_ref": head_branch, "head_sha": "s",
                           "url": f"gitlab://mr/{n}", "title": title}
            return self.prs[n]["url"]
        def find_open_pr_for_story(self, story_id, branch_prefix="auto/"):
            want = f"{branch_prefix}{story_id}-"
            return next((p for p in self.prs.values() if p["head_ref"].startswith(want)), None)
        def list_open_prs(self, branch_prefix=""):
            return [p for p in self.prs.values() if p["head_ref"].startswith(branch_prefix)]
        def find_prs_for_story(self, story_id, branch_prefix="auto/"):
            want = f"{branch_prefix}{story_id}-"
            return [dict(p, state="open", merged=False, updated_at="")
                    for p in self.prs.values() if p["head_ref"].startswith(want)]
        def get_pr_metadata(self, pr_number): return self.prs[pr_number]
        def get_pr_changed_files(self, pr_number): return []
        def reopen_pull_request(self, pr_number): pass
        def post_pr_comment(self, pr_number, body):
            self.comments.setdefault(pr_number, []).append(body)
        def get_pr_comments(self, pr_number): return self.comments.get(pr_number, [])
        def get_workflow_runs(self, workflow_file, branch, limit=20): return []
        def get_run_artifact_file(self, run_id, artifact_prefix, filename): return None
        def get_review_comments(self, pr_number, review_id=None): return []
        def reply_to_review_comment(self, pr_number, comment_id, body): pass

    register_adapter("gitlab_like", GitLabLikeHost)
    host = get_repo_host("gitlab_like", fresh=True)
    assert isinstance(host, RepoHost)

    host.create_branch("auto/S-1-login")
    assert host.branch_exists("auto/S-1-login")
    url = host.open_pull_request("t", "b", "auto/S-1-login")
    assert url.startswith("gitlab://")
    found = host.find_open_pr_for_story("S-1")
    assert found["head_ref"] == "auto/S-1-login"
    host.post_pr_comment(found["number"], "review")
    assert host.get_pr_comments(found["number"]) == ["review"]