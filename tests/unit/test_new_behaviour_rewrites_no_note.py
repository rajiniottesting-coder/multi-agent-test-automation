"""A story that changes nothing existing rewrites no reference note.

3 Nov 2026, validation of SCRUM-283 ("Write a review for a product" - coverage
of a review form the application already has): the story went straight to
ai-ready, so Agent 0 ran the hand-over context update at once. Asked which
notes the story makes UNTRUE, the model narrowed a correct, fuller note
("All three fields are required ... blocked by the browser's own validation")
to the story's own sentence and opened context-update PR #246.

Agent 0 already classifies every requirement story (ChangeSeeds.change_type)
and already trusts new_behaviour to mean "nothing that exists today changes"
(validate_requirement_seeds drops its element seeds). Now the report keeps
that classification, and the context update reads it: a new_behaviour story
gets a "no update needed" marker and no model call. What it ADDS reaches the
notes after its tests merge (the notes addition). Every other change type,
and a report without one (older reports, the pull-request and inventory
triggers), runs the update exactly as before.

Generic stories and files only; no network, no model.
"""
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import agents.agent0_impact as a0
from core import context_update as cu
from core import impact_analysis as ia

STORY = {"summary": "Add a thing", "description": "A visitor can do the thing."}
SETTINGS = {"context_update": {"enabled": True, "branch_prefix": "context-update/"},
            "review": {"summary_prefix": "Impact Review"}}


def _tracker(comments=()):
    t = MagicMock()
    t.get_story.return_value = STORY
    t.get_comments.return_value = list(comments)
    t.get_subtasks.return_value = []
    return t


@pytest.fixture
def spy(monkeypatch):
    """Records whether the model-backed steps ran; they find nothing."""
    calls = []
    monkeypatch.setattr(cu, "context_sources", lambda root: {})
    monkeypatch.setattr(cu, "code_sources", lambda root: {})
    monkeypatch.setattr(cu, "extract_changes",
                        lambda llm, story: calls.append("wording") or [])
    monkeypatch.setattr(cu, "extract_note_rewrites",
                        lambda *a, **k: calls.append("rewrites") or ([], []))
    return calls


# ── the context update ──────────────────────────────────────────────────────

def test_a_new_behaviour_story_gets_a_marker_and_no_model_call(spy, tmp_path):
    tracker = _tracker()
    out = cu.propose_for_story(tracker, MagicMock(), MagicMock(), "AB-9", SETTINGS, tmp_path,
                               change_type="new_behaviour")
    assert out == {"story": "AB-9", "context": "none", "why": "new_behaviour"}
    assert spy == [], "no wording or rewrite call for a story that changes nothing"
    body = tracker.add_comment.call_args.args[1]
    assert body.startswith(cu.MARKER) and "new_behaviour" in body
    assert "notes addition" in body, "says where the new facts go instead"
    assert f"(story: {cu._story_hash(STORY)})" in body


def test_the_marker_stands_for_the_same_story_text(spy, tmp_path):
    tracker = _tracker()
    cu.propose_for_story(tracker, MagicMock(), MagicMock(), "AB-9", SETTINGS, tmp_path,
                         change_type="new_behaviour")
    again = cu.propose_for_story(_tracker([tracker.add_comment.call_args.args[1]]), MagicMock(),
                                 MagicMock(), "AB-9", SETTINGS, tmp_path,
                                 change_type="new_behaviour")
    assert again["context"] == "already-proposed"


@pytest.mark.parametrize("change_type", ["changed_behaviour", "removed_behaviour", "mixed",
                                         None, "", "unexpected"])
def test_every_other_change_type_is_checked_as_before(spy, tmp_path, change_type):
    tracker = _tracker()
    out = cu.propose_for_story(tracker, MagicMock(), MagicMock(), "AB-9", SETTINGS, tmp_path,
                               change_type=change_type)
    assert spy == ["wording", "rewrites"]
    assert out == {"story": "AB-9", "context": "none"}
    assert "makes no passage untrue" in tracker.add_comment.call_args.args[1]


def test_switched_off_stays_off_whatever_the_type(spy, tmp_path):
    out = cu.propose_for_story(_tracker(), MagicMock(), MagicMock(), "AB-9",
                               {"context_update": {"enabled": False}}, tmp_path,
                               change_type="new_behaviour")
    assert out["context"] == "disabled" and spy == []


# ── the report keeps the classification ─────────────────────────────────────

def _report(change_type=None):
    kw = {} if change_type is None else {"change_type": change_type}
    return ia.report_dict("AB-9", "h", "g", [], [], False, ia.Seeds(), [], **kw)


def test_the_report_keeps_the_change_type_and_reads_it_back():
    report = _report("new_behaviour")
    assert report["change_type"] == "new_behaviour"
    assert ia.extract(ia.embed(report))["change_type"] == "new_behaviour"


def test_a_report_without_a_type_is_unchanged():
    """The pull-request and inventory triggers pass none: their report is
    byte-for-byte what it was."""
    assert "change_type" not in _report()
    assert list(_report()) == ["change_ref", "content_hash", "graph_sha", "ranked", "by_owner",
                               "unaffected", "not_judged", "no_component", "seeds",
                               "dropped_assessments"]


def test_the_readable_report_names_the_type():
    text = a0._render_report(_report("new_behaviour"), "Impact report for AB-9")
    assert "Change type: new_behaviour - nothing that exists today changes." in text
    assert "Change type" not in a0._render_report(_report(), "Impact report for AB-9")


def test_analyse_requirement_passes_the_model_classification():
    src = Path(a0.__file__).read_text(encoding="utf-8")
    body = src.split("def analyse_requirement(", 1)[1].split("\ndef ", 1)[0]
    assert "change_type=change.change_type" in body


# ── Agent 0's wiring ────────────────────────────────────────────────────────

def _wire(monkeypatch, published):
    seen = []
    monkeypatch.setattr(cu, "propose_for_story",
                        lambda *a, **k: seen.append(k.get("change_type")) or {"context": "none"})
    monkeypatch.setattr(a0, "_previous_report", lambda *a, **k: (published, None))
    return seen


def test_straight_to_ai_ready_uses_the_report_just_made(monkeypatch, tmp_path):
    seen = _wire(monkeypatch, published={"change_type": "changed_behaviour"})
    monkeypatch.setattr(a0, "_already_analysed", lambda *a, **k: False)
    monkeypatch.setattr(a0, "analyse_requirement",
                        lambda *a, **k: {"change_type": "new_behaviour"})
    monkeypatch.setattr(a0, "publish", lambda *a, **k: {"action": "nothing-to-review"})
    a0.analyse_and_publish(_tracker(), "AB-9", object(), SETTINGS, tmp_path, host=object(),
                           dry_run=True)
    assert seen == ["new_behaviour"], "the in-memory report, not an older published one"


@pytest.mark.parametrize("published, expected", [({"change_type": "new_behaviour"}, "new_behaviour"),
                                                 ({"change_ref": "AB-9"}, None), (None, None)])
def test_the_hand_over_reads_the_published_report(monkeypatch, tmp_path, published, expected):
    seen = _wire(monkeypatch, published)
    out = a0._propose_context(_tracker(), object(), object(), "AB-9", SETTINGS, tmp_path)
    assert seen == [expected] and out["context"] == "none"


def test_an_unreadable_report_runs_the_update_as_before(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(cu, "propose_for_story",
                        lambda *a, **k: seen.append(k.get("change_type")) or {"context": "none"})

    def boom(*a, **k):
        raise RuntimeError("tracker down")
    monkeypatch.setattr(a0, "_previous_report", boom)
    out = a0._propose_context(_tracker(), object(), object(), "AB-9", SETTINGS, tmp_path)
    assert seen == [None] and out["context"] == "none"
