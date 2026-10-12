"""Fixes from the Agent 0 validation series (A1-A3), one block per finding.

F3  the review table shows WHY a test is affected, not every structural path
F4  a re-analysis that changes nothing says so
F5  the context update rewrites reference passages a story makes untrue
F6  the model's verdict caps the tier
F7  a revision that changes its test's purpose, or repeats another, is flagged
F8  absence is never asserted through a predicate that waits for presence
F9  a spliced scenario's marker sits where every generated marker sits

Generic: synthetic pages, keys, files and stories; no network, no model.
"""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from core import context_update as cu
from core import impact_analysis as ia
from core.schemas import (
    GeneratedFile,
    ImpactAwareDraft,
    NoteRewrite,
    NoteRewrites,
    TestCase,
    TestCaseRevision,
    TestStep,
    WordingChanges,
)

for _cls in (TestCase, TestCaseRevision, TestStep):
    _cls.__test__ = False

WEIGHTS = {"structural": 0.45, "component": 0.15, "semantic": 0.15, "adjudicated": 0.25}
THRESHOLDS = {"must_update": 0.6, "review": 0.3}


# ── F6: the model's verdict caps the tier ───────────────────────────

def _cand(cid, structural=1.0, component=1.0, semantic=0.5):
    return SimpleNamespace(id=cid, ref=cid, test_case_key=cid, file="f", title=cid, owner="O",
                           layer=1, structural=structural, component=component,
                           semantic=semantic, paths=[], blocked_by=[])


def _tier(candidate, verdict, signals=("structural", "component", "semantic", "adjudicated")):
    judged = {candidate.id: (verdict, "r", [])} if verdict else {}
    return ia.rank([candidate], judged, WEIGHTS, THRESHOLDS, signals)[0]


def test_a_review_verdict_is_never_raised_to_must_update():
    row = _tier(_cand("C1"), "review")
    assert row["score"] >= THRESHOLDS["must_update"]          # structure alone would say so
    assert row["tier"] == "review"


def test_the_score_can_still_lower_a_judged_tier():
    weak = _cand("C2", structural=0.0, component=0.0, semantic=1.0)
    row = _tier(weak, "must-update")
    assert row["score"] == 0.4 and row["tier"] == "review"


def test_unjudged_candidates_keep_the_score_tier():
    row = _tier(_cand("C3"), None, signals=("structural", "component"))
    assert row["tier"] == "must-update"


def test_must_update_and_unaffected_verdicts_behave_as_before():
    assert _tier(_cand("C4"), "must-update")["tier"] == "must-update"
    assert _tier(_cand("C5"), "unaffected")["tier"] == "unaffected"


# ── F3: one readable evidence line ──────────────────────────────────

ROW = {"reason": "Sets a value the change removes, so the step fails.",
       "evidence": ("element p:a <- P.m <- scenario; element p:a <- P.n <- Then step; "
                    "element q:b <- Q.k <- scenario")}


def test_short_evidence_is_the_reason_and_the_elements():
    from agents.agent0_impact import short_evidence
    text = short_evidence(ROW)
    assert text == "Sets a value the change removes, so the step fails. - Elements: p:a, q:b"


def test_short_evidence_without_a_reason_names_the_elements():
    from agents.agent0_impact import short_evidence
    assert short_evidence({"reason": "", "evidence": ROW["evidence"]}) == "Elements: p:a, q:b"
    long = short_evidence({"reason": "word " * 200, "evidence": ""})
    assert len(long) <= 240 and long.endswith("...")


def test_the_review_table_carries_the_short_line_and_the_data_keeps_the_paths():
    from agents.agent0_impact import _review_rows
    report = {"ranked": [dict(ROW, key="AB-1", ref="AB-1", owner="AB-9", tier="review",
                              score=0.5, blocked_by=[])]}
    row = _review_rows(report)[0]
    assert row["evidence"].startswith("Sets a value") and "<-" not in row["evidence"]
    assert "<-" in report["ranked"][0]["evidence"]


# ── F4: a re-analysis that changes nothing says so ──────────────────

def test_an_unchanged_reanalysis_posts_a_no_change_delta():
    from agents.agent0_impact import DELTA, _post_delta
    tracker = MagicMock()
    _post_delta(tracker, "AB-9", {"added": [], "removed": [], "tier_changed": []})
    body = tracker.add_comment.call_args.args[1]
    assert body.startswith(DELTA) and "no change to the affected tests" in body


def test_a_first_analysis_posts_no_delta():
    from agents.agent0_impact import _post_delta
    tracker = MagicMock()
    _post_delta(tracker, "AB-9", None)
    tracker.add_comment.assert_not_called()


# ── F5: passages a story makes untrue ───────────────────────────────

INVENTORY = {"pages": {"detail": {
    "elements": {"pop": "text=Item added to basket"},
    "elements_notes": {"pop": "A confirmation pop-up reads Item added to basket."}}}}
NOTES = "# Basket\nAdding an item opens a confirmation pop-up.\nUnrelated line.\n"


def _sources():
    return {"inv/app.json": json.dumps(INVENTORY, indent=2) + "\n",
            "prompts/app_context/basket.md": NOTES}


def _rw(path, old, new, reason="AC1: no pop-up any more"):
    return NoteRewrite(path=path, old=old, new=new, reason=reason)


def test_a_note_passage_is_rewritten_and_reported():
    p = cu.propose(_sources(), [], None, [
        _rw("prompts/app_context/basket.md", "Adding an item opens a confirmation pop-up.",
            "Adding an item opens the basket page.")])
    assert "Adding an item opens the basket page." in p.edits["prompts/app_context/basket.md"]
    assert "Unrelated line." in p.edits["prompts/app_context/basket.md"]
    assert p.rewrites[0]["reason"] == "AC1: no pop-up any more"


def test_an_inventory_note_is_rewritten_but_never_a_selector():
    p = cu.propose(_sources(), [], None, [
        _rw("inv/app.json", "Item added to basket", "REMOVED by AB-9: the basket page opens")])
    data = json.loads(p.edits["inv/app.json"])
    page = data["pages"]["detail"]
    assert page["elements"]["pop"] == "text=Item added to basket"           # selector kept
    assert page["elements_notes"]["pop"].startswith("A confirmation pop-up reads REMOVED")


def test_a_passage_not_found_verbatim_is_dropped_and_reported():
    p = cu.propose(_sources(), [], None, [
        _rw("prompts/app_context/basket.md", "Something the file never says.", "x"),
        _rw("prompts/app_context/other.md", "Unrelated line.", "y")])
    assert p.empty and len(p.dropped) == 2
    assert "not in prompts/app_context/basket.md verbatim" in p.dropped[0][2]


def test_the_pr_body_lists_each_rewrite_with_its_reason():
    p = cu.propose(_sources(), [], None, [
        _rw("prompts/app_context/basket.md", "Adding an item opens a confirmation pop-up.",
            "Adding an item opens the basket page.")])
    body = cu.render_body("AB-9", p)
    assert "Passages the story makes untrue" in body and "AC1: no pop-up any more" in body
    assert "Merge only after the change is deployed" in body


def test_the_notes_offered_to_the_model_never_include_a_selector():
    block = cu._notes_block(_sources())
    assert "text=Item added to basket" not in block
    assert "A confirmation pop-up reads" in block and "Unrelated line." in block


class _Host:
    def __init__(self):
        self.files, self.prs = {}, []

    def branch_exists(self, b):
        return False

    def create_branch(self, b, base="main"):
        pass

    def create_or_update_file(self, path, content, msg, branch):
        self.files[path] = content

    def open_pull_request(self, title, body, head, base="main"):
        self.prs.append(body)
        return "https://host.example/pr/2"

    def delete_branch(self, b):
        return True


def _llm(rewrites=None, fail=False):
    def answer(system_prompt="", user_prompt="", output_schema=None):
        if output_schema is NoteRewrites:
            if fail:
                raise RuntimeError("gateway down")
            return NoteRewrites(rewrites=rewrites or [])
        return WordingChanges(changes=[])
    llm = MagicMock()
    llm.invoke_structured.side_effect = answer
    return llm


@pytest.fixture
def notes_repo(tmp_path, monkeypatch):
    for rel, text in _sources().items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text, encoding="utf-8")
    monkeypatch.setattr(cu, "context_sources",
                        lambda root: {r: (Path(root) / r).read_text(encoding="utf-8")
                                      for r in _sources()})
    return tmp_path


SETTINGS = {"context_update": {"enabled": True, "branch_prefix": "context-update/"}}


def _tracker():
    t = MagicMock()
    t.get_comments.return_value = []
    t.get_story.return_value = {"summary": "No pop-up", "description": "AC1: no pop-up any more"}
    return t


def test_a_behaviour_change_now_gets_a_context_pr(notes_repo):
    host = _Host()
    out = cu.propose_for_story(_tracker(), host, _llm([
        _rw("prompts/app_context/basket.md", "Adding an item opens a confirmation pop-up.",
            "Adding an item opens the basket page.")]), "AB-9", SETTINGS, notes_repo)
    assert out["context"] == "proposed"
    assert "opens the basket page" in host.files["prompts/app_context/basket.md"]


def test_a_failed_notes_check_says_so_and_loses_nothing(notes_repo):
    tracker = _tracker()
    out = cu.propose_for_story(tracker, _Host(), _llm(fail=True), "AB-9", SETTINGS, notes_repo)
    assert out["context"] == "none"
    assert "Behaviour notes were not checked" in tracker.add_comment.call_args.args[1]


def test_the_notes_prompt_names_the_story_and_offers_no_selector(notes_repo):
    llm = _llm()
    cu.propose_for_story(_tracker(), _Host(), llm, "AB-9", SETTINGS, notes_repo)
    prompt = next(c.kwargs["user_prompt"] for c in llm.invoke_structured.call_args_list
                  if c.kwargs["output_schema"] is NoteRewrites)
    assert "REMOVED by AB-9" in prompt and "text=Item added to basket" not in prompt


# ── F7: a revision that changes purpose, or repeats another ─────────

def _case(title):
    return TestCase(title=title, description="d", priority="High", test_type="Positive",
                    preconditions=[], steps=[TestStep(step_number=1, action="a",
                                                      expected_result="b")],
                    expected_outcome="ok", test_data=None)


def _validate(new_title, existing=frozenset()):
    from agents.agent1_impact import validate_draft
    draft = ImpactAwareDraft(story_summary="s", new_test_cases=[], revisions=[
        TestCaseRevision(key="AB-1", revised=_case(new_title), change_note="n")])
    return validate_draft(draft, {"AB-1"}, set(existing), {},
                          {"AB-1": "[Positive] Choose a size and confirm the size in the basket"})


def test_a_revision_that_changes_its_purpose_is_flagged():
    errors, near = _validate("[Positive] Add the same item three times and see the count rise")
    assert not errors and any("changed its purpose" in n for n in near)


def test_a_revision_that_keeps_its_purpose_is_not_flagged():
    _e, near = _validate("[Positive] Choose a size and confirm the chosen size in the basket")
    assert not near


def test_a_revision_close_to_another_scenario_is_flagged():
    from agents.agent1_impact import _norm
    other = _norm("Choose a size and confirm the size shown in the basket view")
    _e, near = _validate("[Positive] Choose a size and confirm the size shown in the basket",
                         {other})
    assert any("close to an existing scenario" in n for n in near)


# ── F8: absence through a predicate that waits for presence ─────────

PAGE = '''from pages.base_page import BasePage


class WidgetPage(BasePage):
    def has_badge(self) -> bool:
        return self.is_showing(self.sel("badge"))
{extra}'''

ALT = '''
    def badge_count(self) -> int:
        return self.get_count(self.sel("badge"))
'''


def _steps(body):
    return ("from pytest_bdd import then\n\n\n@then('the badge is gone')\n"
            f"def _(widget_page):\n    {body}\n")


def _absence(step_body, extra=ALT):
    from validators.method_resolution_validator import (
        validate_absence_not_asserted_with_waiting_probe as v,
    )
    files = [GeneratedFile(file_path="pages/widget_page.py", content=PAGE.format(extra=extra),
                           is_new_file=True, purpose="p"),
             GeneratedFile(file_path="tests/step_defs/test_widget.py",
                           content=_steps(step_body), is_new_file=True, purpose="s")]
    return v(files, Path("/nonexistent"))


def test_absence_through_a_waiting_predicate_points_at_the_answer():
    errors = _absence("assert not widget_page.has_badge()")
    assert len(errors) == 1
    assert errors[0].startswith("Absence assertion error in 'tests/step_defs/test_widget.py'")
    assert "WidgetPage.badge_count()" in errors[0]


def test_absence_with_no_answering_method_points_at_the_page_object():
    errors = _absence("assert widget_page.has_badge() is False", extra="")
    assert len(errors) == 1
    assert errors[0].startswith("Absence assertion error in 'pages/widget_page.py'")
    assert 'self.wait_hidden(self.sel("badge"))' in errors[0]


@pytest.mark.parametrize("body", ["assert widget_page.has_badge()",
                                  "assert widget_page.badge_count() == 0"])
def test_presence_and_a_non_waiting_absence_pass(body):
    assert _absence(body) == []


def test_the_absence_rule_is_repairable():
    import inspect

    import agents.agent2_coder as a2
    assert "validate_absence_not_asserted_with_waiting_probe" in \
        inspect.getsource(a2._collect_repairable_errors)
    assert a2._classify_error("Absence assertion error in 'x': ...") == "absence_waits"


# ── F9: the spliced marker sits like every generated marker ─────────

ORIGINAL = ("Feature: F\n\n  @smoke @x\n  # JIRA: AB-1 (hash: 11111111) owner: AB-9\n"
            "  Scenario: old\n    Given a\n\n"
            "  # JIRA: AB-2 (hash: 22222222) owner: AB-9\n  Scenario: two\n    Given b\n")
MODEL = ("# JIRA: AB-1 (hash: 33333333) owner: AB-9 impacted-by: AB-5\n"
         "  Scenario: new\n    Given c\n")


def test_a_spliced_marker_sits_below_the_tags_indented_like_the_scenario():
    from agents.agent2_coder import parse_feature_file, splice_scenario
    out = splice_scenario(ORIGINAL, "AB-1", MODEL, "33333333")
    assert ("  @smoke @x\n  # JIRA: AB-1 (hash: 33333333) owner: AB-9 impacted-by: AB-5\n"
            "  Scenario: new\n") in out
    _h, blocks = parse_feature_file(out)
    assert [b.jira_key for b in blocks if b.kind == "scenario"] == ["AB-1", "AB-2"]


def test_an_appended_marker_is_indented_like_the_scenario():
    from agents.agent2_coder import append_scenario
    out = append_scenario(ORIGINAL, "# JIRA: AB-3 (hash: 44444444) owner: AB-5\n"
                                    "  Scenario: three\n    Given d\n")
    assert out.endswith("\n  # JIRA: AB-3 (hash: 44444444) owner: AB-5\n"
                        "  Scenario: three\n    Given d\n")


# ── after an undo the change story is ready to retry or drop ────────

def _undo(tmp_path, own=("AB-20", "AB-21")):
    from core import impact_reconcile as rec
    from core.impact_settings import impact_settings
    feature = tmp_path / "features" / "f.feature"
    feature.parent.mkdir(parents=True)
    feature.write_text("Feature: F\n\n  # JIRA: AB-21 (hash: 1a2b3c4d) owner: AB-9\n"
                       "  Scenario: shipped earlier\n    Given a\n", encoding="utf-8")
    tracker = MagicMock()
    tracker.get_linked_test_cases.return_value = [{"key": k} for k in own]
    tracker.get_comments.return_value = []
    settings = impact_settings()
    out = rec._revert(tracker, "AB-9", {"number": 7, "url": "u"}, [], {},
                      settings["labels"], settings, features_dir=tmp_path / "features")
    return tracker, out, settings


def test_own_tests_that_never_reached_main_are_retired_others_kept(tmp_path):
    tracker, out, _s = _undo(tmp_path)
    assert out["retired_own"] == ["AB-20"]                     # AB-21 has a scenario on main
    labelled = [c.args for c in tracker.add_label.call_args_list]
    assert ("AB-20", "ai-retired") in labelled and ("AB-21", "ai-retired") not in labelled


def test_progress_labels_come_off_and_the_story_says_how_to_retry(tmp_path):
    tracker, _out, settings = _undo(tmp_path)
    removed = {c.args[1] for c in tracker.remove_label.call_args_list if c.args[0] == "AB-9"}
    assert set(settings["reconcile"]["reset_labels"]) <= removed
    body = next(c.args[1] for c in tracker.add_comment.call_args_list if c.args[0] == "AB-9")
    assert body.startswith("[agent0:reconcile] reverted pr: 7")
    assert "AB-20" in body and "To retry: remove impact-reverted and add impact-check" in body


def test_the_card_follows_the_reverted_label(tmp_path, monkeypatch):
    import core.board_status as bs
    moved = []
    monkeypatch.setattr(bs, "move_card_for_label", lambda t, key, label: moved.append((key, label)))
    _undo(tmp_path)
    assert moved == [("AB-9", "impact-reverted")]


def test_an_unreadable_main_retires_nothing(tmp_path):
    from core import impact_reconcile as rec
    assert rec._unautomated(["AB-20"], tmp_path / "missing") == []
