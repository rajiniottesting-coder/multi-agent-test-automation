"""A change story undone by reconcile can be retried - and the retry is its own attempt.

Found while preparing to re-run validation story A3: after an undo, reconcile
tells a person "remove impact-reverted and add impact-check" to retry. Three
things made that retry fail or misbehave:

  1. Agent 0's repeat check read the undone (Done) Impact Review and reported
     the unchanged story as "already analysed" - the retry did nothing.
  2. Reconcile looked at every PR the story ever had, so the closed PR of the
     earlier attempt could undo the retry's fresh revisions before its own PR
     existed (and an earlier merged PR could "finish" it).
  3. The context update's "already proposed" marker from the earlier attempt
     blocked a new context check, even when the story text had changed.

Generic: synthetic stories and PRs; no application names.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from core import context_update as cu
from core import impact_reconcile as rec
from core import impact_trace
from core.impact_settings import impact_settings
from tests.unit.test_agent2_impact import _hand_over_and_draft, _run_agent2, world  # noqa: F401

NOW = datetime(2026, 10, 10, tzinfo=timezone.utc)


# ── the attempt stamp ───────────────────────────────────────────────

def test_the_latest_applied_stamp_wins_and_none_without_one():
    early = impact_trace.applied_line(NOW)
    late = impact_trace.applied_line(NOW + timedelta(days=2))
    assert impact_trace.latest_applied(["x", f"[agent1:impact-draft] d\n{early}", late]) \
        == NOW + timedelta(days=2)
    assert impact_trace.latest_applied(["no stamp here"]) is None


def test_a_pr_without_created_at_or_a_story_without_stamp_counts():
    assert rec._in_attempt({"number": 1}, NOW)
    assert rec._in_attempt({"number": 1, "created_at": "2026-01-01T00:00:00+00:00"}, None)
    assert not rec._in_attempt({"created_at": "2026-10-09T23:59:59+00:00"}, NOW)
    assert rec._in_attempt({"created_at": "2026-10-10T00:00:01Z"}, NOW)


def test_agent1_stamps_the_attempt_only_when_it_changed_something(world):    # noqa: F811
    fake, jira, _root = world
    _hand_over_and_draft(jira, {"SBX-11": "approve"}, new=())
    gates = [c for c in fake.comments["SBX-5"] if c.startswith("[agent1:impact-draft]")]
    assert impact_trace.APPLIED in gates[-1]
    _hand_over_and_draft(jira, {"SBX-11": "approve"}, new=())        # same text again
    gates = [c for c in fake.comments["SBX-5"] if c.startswith("[agent1:impact-draft]")]
    assert impact_trace.APPLIED not in gates[-1]        # nothing revised: same attempt


# ── reconcile settles the retry on the retry's own PR ───────────────

def _pr_created(gh, number, when):
    gh.prs[number - 1]["created_at"] = when.isoformat()


def test_an_earlier_attempts_closed_pr_never_undoes_a_retry(world):          # noqa: F811
    fake, jira, root = world
    _hand_over_and_draft(jira, {"SBX-11": "approve"}, new=())
    _r, gh, *_ = _run_agent2(jira, root)
    _pr_created(gh, 1, datetime(2020, 1, 1, tzinfo=timezone.utc))   # long before this attempt
    gh.close(1)
    revised = fake.issues["SBX-11"]["description"]
    for _ in range(3):                                   # however many scans run
        out = rec.reconcile_story(jira, gh, "SBX-5", now=NOW)
        assert out["action"] in ("no-pr-noted", "waiting-for-pr")
    assert fake.issues["SBX-11"]["description"] == revised          # nothing undone
    assert "impact-applied" in fake.issues["SBX-5"]["labels"]


def test_an_earlier_attempts_merged_pr_never_finishes_a_retry(world):        # noqa: F811
    fake, jira, root = world
    _hand_over_and_draft(jira, {"SBX-11": "approve"}, new=())
    _r, gh, *_ = _run_agent2(jira, root)
    _pr_created(gh, 1, datetime(2020, 1, 1, tzinfo=timezone.utc))
    gh.merge(1)
    assert rec.reconcile_story(jira, gh, "SBX-5", now=NOW)["action"] == "no-pr-noted"
    assert "impact-applied" in fake.issues["SBX-5"]["labels"]


def test_this_attempts_pr_is_still_settled(world):                          # noqa: F811
    fake, jira, root = world
    _hand_over_and_draft(jira, {"SBX-11": "approve"}, new=())
    _r, gh, *_ = _run_agent2(jira, root)
    _pr_created(gh, 1, datetime.now(timezone.utc) + timedelta(minutes=1))
    gh.merge(1)
    assert rec.reconcile_story(jira, gh, "SBX-5", now=NOW)["action"] == "merged"


# ── the undone review no longer counts ──────────────────────────────

def test_the_undo_marks_the_review_undone_and_says_so(tmp_path):
    tracker = MagicMock()
    tracker.get_linked_test_cases.return_value = []
    tracker.get_comments.return_value = []
    tracker.get_subtasks.return_value = [
        {"key": "AB-30", "summary": "Impact Review: AB-9", "status": "Done", "description": "d"},
        {"key": "AB-31", "summary": "Other work", "status": "To Do", "description": "e"}]
    settings = impact_settings()
    out = rec._revert(tracker, "AB-9", {"number": 7, "url": "u"}, [], {},
                      settings["labels"], settings, features_dir=tmp_path)
    tracker.set_description.assert_called_once_with(
        "AB-30", "d", summary="[undone PR #7] Impact Review: AB-9")
    assert out["review_undone"] == "AB-30"
    body = next(c.args[1] for c in tracker.add_comment.call_args_list if c.args[0] == "AB-9")
    assert "AB-30 is marked undone" in body
    # what every reader of reviews filters on no longer matches
    assert not "[undone PR #7] Impact Review: AB-9".startswith(settings["review"]["summary_prefix"])


def test_a_failed_review_rename_never_fails_the_undo(tmp_path):
    tracker = MagicMock()
    tracker.get_linked_test_cases.return_value = []
    tracker.get_comments.return_value = []
    tracker.get_subtasks.side_effect = RuntimeError("tracker down")
    settings = impact_settings()
    out = rec._revert(tracker, "AB-9", {"number": 7, "url": "u"}, [], {},
                      settings["labels"], settings, features_dir=tmp_path)
    assert out["action"] == "reverted" and out["review_undone"] is None


def test_a_retry_of_an_unchanged_story_is_analysed_again():
    import agents.agent0_impact as a0
    settings = impact_settings()
    tracker = MagicMock()
    tracker.get_subtasks.return_value = [
        {"key": "AB-30", "summary": "[undone PR #7] Impact Review: AB-9",
         "status": "Done", "description": "irrelevant"}]
    tracker.get_comments.return_value = []
    assert a0._already_analysed(tracker, "AB-9", "anyhash", settings) is False


# ── the context check follows the story text and the attempt ────────

STORY = {"summary": "s", "description": "d", "components": ["C"]}


def test_a_marker_for_this_text_and_attempt_stands():
    h = cu._story_hash(STORY)
    assert cu._already_proposed([f"{cu.MARKER} No context update needed.\n(story: {h})"], h)


def test_an_edited_story_is_checked_again():
    old = cu._story_hash(STORY)
    new = cu._story_hash(dict(STORY, description="d, edited"))
    assert not cu._already_proposed([f"{cu.MARKER} proposed.\n(story: {old})"], new)


def test_a_marker_from_before_an_undo_does_not_count():
    h = cu._story_hash(STORY)
    comments = [f"{cu.MARKER} proposed.\n(story: {h})",
                "[agent0:reconcile] reverted pr: 7\nPull request #7 was closed..."]
    assert not cu._already_proposed(comments, h)
    assert cu._already_proposed(comments + [f"{cu.MARKER} again.\n(story: {h})"], h)


def test_a_marker_without_a_story_hash_cannot_vouch_for_the_text():
    assert not cu._already_proposed([f"{cu.MARKER} No context update needed."], "abc123")


def test_the_marker_written_carries_the_story_hash(tmp_path, monkeypatch):
    tracker = MagicMock()
    tracker.get_comments.return_value = []
    tracker.get_story.return_value = STORY
    monkeypatch.setattr(cu, "context_sources", lambda root: {})
    monkeypatch.setattr(cu, "code_sources", lambda root: {})
    monkeypatch.setattr(cu, "extract_changes", lambda llm, story: [])
    monkeypatch.setattr(cu, "extract_note_rewrites", lambda *a, **k: [])
    out = cu.propose_for_story(tracker, MagicMock(), MagicMock(), "AB-9",
                               {"context_update": {"enabled": True}}, tmp_path)
    assert out["context"] == "none"
    body = tracker.add_comment.call_args.args[1]
    assert body.startswith(cu.MARKER) and f"(story: {cu._story_hash(STORY)})" in body
