"""A context-update marker stands only while its pull request is open.

Found in validation story A3 (retry on 14 Oct): after an undo, a manual
clean-up deleted the `[agent0:reconcile] reverted` comment but kept the old
`[agent0:context-update]` marker, whose PR had been closed unmerged. The
story text was unchanged, so the marker matched, nothing marked the undo,
and the retry's context update was skipped silently.

The pull request's state now decides, not comment history. Synthetic story
and PR numbers; no application names.
"""
from unittest.mock import MagicMock

from core import context_update as cu

STORY = {"summary": "s", "description": "d", "components": ["C"]}
H = cu._story_hash(STORY)
WITH_PR = (f"{cu.MARKER} Context update proposed: https://host.example/o/r/pull/77 - "
           f"3 change(s) to the inventory and context notes.\n(story: {H})")
NO_PR = f"{cu.MARKER} No context update needed: nothing to change.\n(story: {H})"


def _host(state=None, error=None):
    host = MagicMock()
    if error:
        host.get_pr_metadata.side_effect = error
    else:
        host.get_pr_metadata.return_value = {"number": 77, "state": state}
    return host


def test_a_marker_whose_pr_is_open_stands():
    assert cu._already_proposed([WITH_PR], H, cu._pr_is_open(_host("open")))


def test_a_marker_whose_pr_was_closed_does_not_stand():
    """The A3 case: undo comment deleted, closed PR's marker kept."""
    host = _host("closed")
    assert not cu._already_proposed([WITH_PR], H, cu._pr_is_open(host))
    host.get_pr_metadata.assert_called_once_with(77)


def test_a_marker_without_a_pr_stands_on_the_hash_alone():
    host = _host("closed")
    assert cu._already_proposed([NO_PR], H, cu._pr_is_open(host))
    host.get_pr_metadata.assert_not_called()


def test_an_unreadable_pr_counts_as_open_so_no_duplicate_is_opened():
    assert cu._already_proposed([WITH_PR], H, cu._pr_is_open(_host(error=RuntimeError("down"))))


def test_the_undo_rule_still_applies():
    comments = [WITH_PR, "[agent0:reconcile] reverted pr: 9\nclosed without merging"]
    assert not cu._already_proposed(comments, H, cu._pr_is_open(_host("open")))


def test_a_later_marker_for_an_open_pr_stands_after_a_closed_one():
    later = WITH_PR.replace("/pull/77", "/pull/78")
    host = MagicMock()
    host.get_pr_metadata.side_effect = lambda n: {"number": n, "state": "open" if n == 78 else "closed"}
    assert cu._already_proposed([WITH_PR, later], H, cu._pr_is_open(host))


def test_the_a3_retry_proposes_again(tmp_path, monkeypatch):
    """End to end through propose_for_story: the closed PR's marker no longer
    blocks, so the update is proposed and a new marker is written."""
    tracker = MagicMock()
    tracker.get_story.return_value = STORY
    tracker.get_comments.return_value = [WITH_PR]
    host = _host("closed")
    monkeypatch.setattr(cu, "context_sources", lambda root: {})
    monkeypatch.setattr(cu, "code_sources", lambda root: {})
    monkeypatch.setattr(cu, "extract_changes", lambda llm, story: [])
    monkeypatch.setattr(cu, "extract_note_rewrites", lambda *a, **k: [])
    out = cu.propose_for_story(tracker, host, MagicMock(), "AB-9",
                               {"context_update": {"enabled": True}}, tmp_path)
    assert out["context"] == "none"              # checked again, not 'already-proposed'
    assert tracker.add_comment.called


def test_an_open_pr_still_blocks_a_second_proposal(tmp_path):
    tracker = MagicMock()
    tracker.get_story.return_value = STORY
    tracker.get_comments.return_value = [WITH_PR]
    out = cu.propose_for_story(tracker, _host("open"), MagicMock(), "AB-9",
                               {"context_update": {"enabled": True}}, tmp_path)
    assert out["context"] == "already-proposed"
    tracker.add_comment.assert_not_called()
