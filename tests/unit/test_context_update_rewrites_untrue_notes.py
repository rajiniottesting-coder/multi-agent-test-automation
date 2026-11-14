"""The context update rewrites the reference passages a change story makes
untrue: context notes and inventory notes (never a selector), a passage not
found verbatim is dropped and reported, the pull request lists each rewrite
with its reason, and a behaviour change gets a context pull request too.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock
import pytest
from core import context_update as cu
from core.schemas import NoteRewrite, NoteRewrites, WordingChanges


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
