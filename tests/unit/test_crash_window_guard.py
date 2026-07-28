"""Unit tests for the Agent 2 crash-window guard.

`ai-coded` is added only AFTER create_pull_request() succeeds, so a runner
killed between those two calls leaves the story looking un-coded. The next tick
would redo the whole story - a full set of LLM calls thrown away, then a failure
at PR creation because the PR already exists.

An open auto/<STORY>-* PR is treated as the completion marker: it means the work
landed and only the label is missing.
"""
from unittest.mock import MagicMock, PropertyMock, patch

from agents.github_client import GitHubClient


def _pr(ref, number):
    m = MagicMock()
    m.head.ref = ref
    m.number = number
    return m


def _client(prs, boom=False):
    gh = GitHubClient.__new__(GitHubClient)
    repo = MagicMock()
    if boom:
        repo.get_pulls.side_effect = Exception("api down")
    else:
        repo.get_pulls.return_value = prs
    return gh, repo


def _find(gh, repo, story):
    with patch.object(GitHubClient, "repo", new_callable=PropertyMock,
                      return_value=repo):
        return gh.find_open_pr_for_story(story)


def test_finds_pr_for_the_story():
    gh, repo = _client([_pr("auto/SCRUM-9-cart", 9),
                        _pr("auto/SCRUM-5-login", 42)])
    assert _find(gh, repo, "SCRUM-5").number == 42


def test_ignores_other_stories():
    gh, repo = _client([_pr("auto/SCRUM-5-login", 42)])
    assert _find(gh, repo, "SCRUM-7") is None


def test_matches_rev_and_update_branches():
    """-revN / -updateN belong to the same story."""
    for ref in ("auto/SCRUM-5-login-rev2", "auto/SCRUM-5-login-update3"):
        gh, repo = _client([_pr(ref, 43)])
        assert _find(gh, repo, "SCRUM-5").number == 43


def test_ignores_non_auto_branches():
    """A human's hand-written branch must never be mistaken for agent output."""
    gh, repo = _client([_pr("feature/SCRUM-5-manual-fix", 44)])
    assert _find(gh, repo, "SCRUM-5") is None


def test_prefix_is_not_a_substring_match():
    """SCRUM-5 must not match SCRUM-50."""
    gh, repo = _client([_pr("auto/SCRUM-50-checkout", 50)])
    assert _find(gh, repo, "SCRUM-5") is None


def test_api_failure_never_blocks():
    """A lookup problem must not stop the agent - degrade to 'no PR found'."""
    gh, repo = _client([], boom=True)
    assert _find(gh, repo, "SCRUM-5") is None


# ── WINDOW A: partial commits, no PR -> discard the branch ────

def _gh_with_branch(exists: bool, delete_ok: bool = True):
    gh = GitHubClient.__new__(GitHubClient)
    repo = MagicMock()
    if exists:
        repo.get_git_ref.return_value = MagicMock()
    else:
        repo.get_git_ref.side_effect = Exception("404 not found")
    if not delete_ok:
        repo.get_git_ref.return_value.delete.side_effect = Exception("no perms")
    return gh, repo


def test_delete_branch_removes_partial_branch():
    gh, repo = _gh_with_branch(exists=True)
    with patch.object(GitHubClient, "repo", new_callable=PropertyMock,
                      return_value=repo):
        assert gh.delete_branch("auto/SCRUM-5-login") is True
    repo.get_git_ref.assert_called_once_with("heads/auto/SCRUM-5-login")


def test_delete_branch_reports_failure_without_raising():
    """A permissions problem must not crash the agent mid-run."""
    gh, repo = _gh_with_branch(exists=True, delete_ok=False)
    with patch.object(GitHubClient, "repo", new_callable=PropertyMock,
                      return_value=repo):
        assert gh.delete_branch("auto/SCRUM-5-login") is False


def test_delete_branch_on_missing_branch_is_not_an_error():
    gh, repo = _gh_with_branch(exists=False)
    with patch.object(GitHubClient, "repo", new_callable=PropertyMock,
                      return_value=repo):
        assert gh.delete_branch("auto/SCRUM-5-nope") is False