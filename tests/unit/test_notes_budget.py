"""F-9: the app notes stay within a size budget and say each thing once.

Each prompts/app_context module goes into the prompt of every story it is
selected for (core.md into every Agent 1 call). Nothing measured them, so the
notes only ever grew - and with the merge-time additions (F-8) they grow by
design. Now: a module over `context_update.module_budget_chars` fails this
suite (a notes PR that grows one too far must condense it first), the
addition PR reports size and repeated sentences, and the onboarding check
warns. Repetition is a warning, never a failure: two modules may legitimately
cross-reference.

Generic notes in the fixtures; the gate itself reads the committed modules.
"""
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

from core import context_update as cu
from core.onboarding import OK, WARN, notes_checks, run_checks
from core.schemas import NoteAddition, NoteAdditions

ROOT = Path(__file__).resolve().parents[2]


def _budget() -> int:
    cfg = yaml.safe_load((ROOT / "config/config.yaml").read_text(encoding="utf-8"))
    return int(cfg["agents"]["agent0_impact"]["context_update"]["module_budget_chars"])


# ── the gate on the committed notes ─────────────────────────────────────

def test_every_committed_notes_module_is_within_its_budget():
    """A notes PR that pushes a module over the budget fails here: condense the
    module in the same PR (it goes into every prompt it is selected for)."""
    budget = _budget()
    folder = ROOT / "prompts" / "app_context"
    over = {p.name: len(p.read_text(encoding="utf-8"))
            for p in sorted(folder.glob("*.md"))
            if len(p.read_text(encoding="utf-8")) > budget}
    assert not over, f"over the {budget}-character budget - condense: {over}"


# ── measuring ───────────────────────────────────────────────────────────

def test_wrapped_lines_are_one_paragraph_and_each_bullet_its_own():
    text = ("# T\n\nA sentence that is\nwrapped over two lines. And a second.\n\n"
            "- first bullet\n  continued\n- second bullet\n")
    assert cu._paragraphs(text) == ["A sentence that is wrapped over two lines. And a second.",
                                    "first bullet continued", "second bullet"]
    assert cu._units(text)[:2] == ["A sentence that is wrapped over two lines.", "And a second."]


def test_the_report_finds_modules_over_budget_and_repeated_sentences():
    texts = {"a.md": "# A\n\nA saved basket survives a sign out and a new session.\n",
             "b.md": "# B\n\n- A saved basket survives a new session and a sign out.\n"
                     + "x" * 200,
             "inv.json": "{" + "y" * 500 + "}"}
    report = cu.notes_report(texts, budget=150)
    assert report["over"] == [("b.md", len(texts["b.md"]))]
    assert len(report["duplicates"]) == 1 and report["duplicates"][0][0] == "a.md"


def test_short_sentences_are_never_reported_as_repeats():
    texts = {"a.md": "Click save.\n", "b.md": "Click save.\n"}
    assert cu.notes_report(texts, budget=1000)["duplicates"] == []


def test_the_report_section_is_empty_when_all_is_well():
    assert cu.render_notes_report({"over": [], "duplicates": []}, 8000) == ""
    text = cu.render_notes_report({"over": [("m.md", 9000)],
                                   "duplicates": [("a.md", "s1", "b.md", "s2")] * 12}, 8000)
    assert "over the 8000-character budget" in text and "`m.md`: 9000 characters" in text
    assert "… and 2 more" in text


# ── reported in the notes-addition PR ───────────────────────────────────

def test_an_addition_that_pushes_a_module_over_budget_says_so(tmp_path, monkeypatch):
    folder = tmp_path / "prompts" / "app_context"
    folder.mkdir(parents=True)
    (folder / "basket.md").write_text("# Basket\n\n" + "Paying needs an address. " * 6 + "\n")
    monkeypatch.setattr(cu, "context_sources",
                        lambda root: {"prompts/app_context/basket.md":
                                      (folder / "basket.md").read_text()})
    llm = MagicMock()
    llm.invoke_structured.return_value = NoteAdditions(additions=[NoteAddition(
        path="prompts/app_context/basket.md", heading="",
        text="- A coupon expires seven days after it is issued.", reason="AC1")])
    tracker = MagicMock()
    tracker.get_comments.return_value = []
    tracker.get_story.return_value = {"summary": "s", "description": "d",
                                      "components": ["Basket"]}
    tracker.get_linked_test_cases.return_value = []
    host = MagicMock()
    host.branch_exists.return_value = False
    settings = {"context_update": {"enabled": True, "additions": True,
                                   "module_budget_chars": 100}}
    out = cu.propose_addition_for_story(tracker, host, llm, "AB-5", settings, tmp_path,
                                        dry_run=True)
    assert "over the 100-character budget" in out["body"]


# ── the onboarding check ────────────────────────────────────────────────

def _notes(tmp_path, files, budget=None):
    folder = tmp_path / "prompts" / "app_context"
    folder.mkdir(parents=True)
    for name, text in files.items():
        (folder / name).write_text(text)
    if budget:
        (tmp_path / "config").mkdir()
        (tmp_path / "config" / "config.yaml").write_text(yaml.safe_dump(
            {"agents": {"agent0_impact": {"context_update": {"module_budget_chars": budget}}}}))
    return tmp_path


def test_onboarding_passes_small_distinct_notes(tmp_path):
    checks = notes_checks(_notes(tmp_path, {"core.md": "# C\n\nShared facts only here.\n"}))
    assert [(c.name, c.status) for c in checks] == [("notes: size", OK)]


def test_onboarding_warns_on_size_and_repetition_with_the_configured_budget(tmp_path):
    root = _notes(tmp_path, {"a.md": "A saved basket survives a sign out and a new session.\n",
                             "b.md": "A saved basket survives a new session and a sign out.\n"},
                  budget=20)
    checks = {c.name: c for c in notes_checks(root)}
    assert checks["notes: size"].status == WARN and "20-character budget" in checks["notes: size"].detail
    assert checks["notes: repetition"].status == WARN


def test_onboarding_warns_when_there_are_no_notes_and_reads_a_single_file(tmp_path):
    assert notes_checks(tmp_path)[0].status == WARN
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "app_context.md").write_text("# Notes\n\nShort.\n")
    assert notes_checks(tmp_path)[0].status == OK


def test_the_full_onboarding_run_includes_the_notes_checks():
    names = {c.name for c in run_checks(ROOT)}
    assert "notes: size" in names


def test_the_budget_is_configured_and_equal_to_the_default():
    from core.impact_settings import DEFAULTS
    assert _budget() == DEFAULTS["context_update"]["module_budget_chars"]
