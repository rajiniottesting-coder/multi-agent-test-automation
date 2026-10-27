"""F-10: the context update reads only what the story's Components select.

Before it, the note-rewrite call sent every app-context module and every
inventory note, whatever the story touched - while Agent 1, drafting the same
story, read only core.md and the story's modules by its own private rule. Now
one rule (core.app_context.select_note_modules / selected_page_names) serves
both, and a rewrite of a file the model was not shown is dropped.

Generic modules and pages only; no application names.
"""
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core import context_update as cu
from core.app_context import select_note_modules, selected_page_names
from core.schemas import NoteRewrite, NoteRewrites, WordingChanges

INVENTORY = {
    "app_name": "Shop",
    "test_users": {"_note": "Shared accounts keep their state."},
    "pages": {
        "menu": {"always": True, "elements": {"home": "#home"},
                 "elements_notes": {"home": "The menu is on every page."}},
        "basket": {"components": ["Basket"], "elements": {"pay": "#pay"},
                   "elements_notes": {"pay": "Paying needs an address."}},
        "profile": {"components": ["User Profile"], "elements": {"save": "#save"},
                    "elements_notes": {"save": "Saving shows a toast."}},
    },
}
MODULES = {"core.md": "# Core\nShared facts.\n",
           "basket.md": "# Basket\nAdding an item opens a confirmation pop-up.\n",
           "user_profile.md": "# Profile\nThe profile keeps one address.\n"}


@pytest.fixture
def repo(tmp_path):
    folder = tmp_path / "prompts" / "app_context"
    folder.mkdir(parents=True)
    for name, text in MODULES.items():
        (folder / name).write_text(text, encoding="utf-8")
    (tmp_path / "inv").mkdir()
    (tmp_path / "inv" / "app.json").write_text(json.dumps(INVENTORY, indent=2) + "\n")
    return tmp_path


def _sources(root):
    out = {"inv/app.json": (root / "inv" / "app.json").read_text()}
    for name in MODULES:
        out[f"prompts/app_context/{name}"] = (root / "prompts" / "app_context" / name).read_text()
    return out


# ── the one selection rule ──────────────────────────────────────────────

@pytest.mark.parametrize("components, expected", [
    (["Basket"], ["core", "basket"]),
    (["basket", "BASKET"], ["core", "basket"]),
    (["user-profile"], ["core", "user_profile"]),
    (["Basket", "Unknown"], ["core", "basket"]),
    (["Unknown"], ["core", "basket", "user_profile"]),
    ([], ["core", "basket", "user_profile"]),
    (None, ["core", "basket", "user_profile"]),
])
def test_select_note_modules(repo, components, expected):
    paths = select_note_modules(repo / "prompts" / "app_context", components)
    assert [p.stem for p in paths] == expected


def test_agent1_and_the_context_update_read_the_same_modules(repo, monkeypatch):
    import agents.agent1_analyst as a1
    monkeypatch.setattr(a1, "PROMPTS_DIR", repo / "prompts")
    block = a1.load_app_context_block(["Basket"])
    offered, _ = cu.scoped_sources(_sources(repo), ["Basket"], repo)
    for name, text in MODULES.items():
        assert (text in block) == (f"prompts/app_context/{name}" in offered), name


@pytest.mark.parametrize("components, expected", [
    (["Basket"], {"menu", "basket"}),
    (["Unknown"], {"menu", "basket", "profile"}),
    ([], {"menu", "basket", "profile"}),
])
def test_selected_page_names_follows_the_inventory_filter(components, expected):
    assert selected_page_names(INVENTORY, components) == expected
    from core.app_context import filter_inventory_by_components
    assert set(filter_inventory_by_components(INVENTORY, components)["pages"]) == expected


# ── what the rewrite call is shown ──────────────────────────────────────

def test_the_notes_block_holds_only_the_selected_modules_and_pages(repo):
    offered, pages = cu.scoped_sources(_sources(repo), ["Basket"], repo)
    block = cu._notes_block(offered, pages)
    assert "Adding an item opens a confirmation pop-up." in block and "Shared facts." in block
    assert "The profile keeps one address." not in block, "another Component's module"
    assert "Paying needs an address." in block and "The menu is on every page." in block
    assert "Saving shows a toast." not in block, "another Component's page notes"
    assert "Shared accounts keep their state." in block, "notes outside pages always offered"
    assert "#pay" not in block, "never a selector"


def test_a_rewrite_of_a_file_the_model_was_not_shown_is_dropped(repo):
    sources = _sources(repo)
    offered, _ = cu.scoped_sources(sources, ["Basket"], repo)
    prop = cu.propose(sources, [], None, [NoteRewrite(
        path="prompts/app_context/user_profile.md", old="The profile keeps one address.",
        new="The profile keeps three addresses.", reason="x")], set(offered))
    assert prop.empty
    assert "not among the notes the story's Components select" in prop.dropped[0][2]


def test_without_a_scope_every_file_stays_rewritable(repo):
    prop = cu.propose(_sources(repo), [], None, [NoteRewrite(
        path="prompts/app_context/user_profile.md", old="The profile keeps one address.",
        new="The profile keeps three addresses.", reason="x")])
    assert "three addresses" in prop.edits["prompts/app_context/user_profile.md"]


def test_the_change_story_call_is_scoped_end_to_end(repo, monkeypatch):
    monkeypatch.setattr(cu, "context_sources", lambda root: _sources(Path(root)))
    seen = {}

    def answer(system_prompt="", user_prompt="", output_schema=None):
        if output_schema is NoteRewrites:
            seen["prompt"] = user_prompt
            return NoteRewrites(rewrites=[])
        return WordingChanges(changes=[])
    llm = MagicMock()
    llm.invoke_structured.side_effect = answer
    tracker = MagicMock()
    tracker.get_comments.return_value = []
    tracker.get_story.return_value = {"summary": "Basket", "description": "AC1",
                                      "components": ["Basket"]}
    cu.propose_for_story(tracker, MagicMock(), llm, "AB-9",
                         {"context_update": {"enabled": True}}, repo)
    assert "confirmation pop-up" in seen["prompt"]
    assert "The profile keeps one address." not in seen["prompt"]


def test_the_single_file_layout_is_always_offered(tmp_path):
    (tmp_path / "prompts").mkdir()
    sources = {"prompts/app_context.md": "# Notes\nAll in one file.\n",
               "inv/app.json": json.dumps(INVENTORY)}
    offered, pages = cu.scoped_sources(sources, ["Basket"], tmp_path)
    assert "prompts/app_context.md" in offered and pages == {"menu", "basket"}
