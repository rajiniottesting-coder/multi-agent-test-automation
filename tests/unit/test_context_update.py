"""Context update: a change story's wording reaches the inventory and the notes.

No agent wrote the inventory or the app context notes. A story that renames
user-visible text left a selector matching the old text (broken after
deployment) and notes teaching the agents the old wording. Agent 0 now
proposes the update as a pull request at hand-over. These tests pin the
replacement, its limits, the branch rule and the Agent 0 wiring.

Generic files and keys only; no network, no model.
"""
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from config import extract_jira_key
from core import context_update as cu
from core.schemas import WordingChange, WordingChanges

INVENTORY = {
    "description": "A shop: browse and Press Me.",
    "pages": {
        "listing": {
            "elements": {"buy_buttons": "text=Press Me", "title": "h1.title"},
            "elements_notes": {"buy_buttons": "Each card renders Press Me twice."},
        },
        "detail": {"elements": {"buy": "button.buy"}},
    },
}


def _sources():
    return {
        "inv/app.json": json.dumps(INVENTORY, indent=2) + "\n",
        "prompts/app_context/a.md": "# A\nClicking \"Press Me\" opens a dialog.\nUnrelated line.\n",
        "prompts/app_context/b.md": "Nothing to see.\n",
    }


def _ch(old, new):
    return WordingChange(old=old, new=new)


def test_selectors_and_notes_are_replaced_and_classified():
    p = cu.propose(_sources(), [_ch("Press Me", "Tap Me")])
    assert sorted(p.edits) == ["inv/app.json", "prompts/app_context/a.md"]
    data = json.loads(p.edits["inv/app.json"])
    assert data["pages"]["listing"]["elements"]["buy_buttons"] == "text=Tap Me"
    assert data["pages"]["listing"]["elements"]["title"] == "h1.title"
    assert data["pages"]["detail"]["elements"]["buy"] == "button.buy"
    kinds = {(f["path"], f["where"]): f["kind"] for f in p.findings}
    assert kinds[("inv/app.json", "pages.listing.elements.buy_buttons")] == "selector"
    assert kinds[("inv/app.json", "pages.listing.elements_notes.buy_buttons")] == "inventory note"
    assert kinds[("inv/app.json", "description")] == "inventory note"
    assert kinds[("prompts/app_context/a.md", "line 2")] == "context note"
    assert "Unrelated line." in p.edits["prompts/app_context/a.md"]


def test_the_inventory_keeps_its_own_formatting():
    src = _sources()
    p = cu.propose(src, [_ch("Press Me", "Tap Me")])
    before, after = src["inv/app.json"].splitlines(), p.edits["inv/app.json"].splitlines()
    assert len(before) == len(after)
    assert sum(a != b for a, b in zip(before, after)) == 3


def test_matching_is_exact_and_case_sensitive():
    p = cu.propose(_sources(), [_ch("press me", "tap me")])
    assert p.empty and p.dropped and "none of the context files" in p.dropped[0][2]


@pytest.mark.parametrize("old,new", [("", "x"), ("x", ""), ("Same", "Same")])
def test_empty_or_unchanged_pairs_are_dropped(old, new):
    p = cu.propose(_sources(), [_ch(old, new)])
    assert p.empty and p.dropped


def test_a_key_containing_the_text_is_never_renamed():
    src = {"inv/app.json": json.dumps({"Press Me": {"elements": {"k": "text=Press Me"}}}, indent=2)}
    data = json.loads(cu.propose(src, [_ch("Press Me", "Tap Me")]).edits["inv/app.json"])
    assert data == {"Press Me": {"elements": {"k": "text=Tap Me"}}}


def test_code_is_listed_not_edited():
    code = {"features/x.feature": "When I click \"Press Me\"\n"}
    p = cu.propose(_sources(), [_ch("Press Me", "Tap Me")], code)
    assert "features/x.feature" not in p.edits
    assert p.code_mentions == [{"path": "features/x.feature", "line": 1,
                                "text": "When I click \"Press Me\""}]


def test_the_branch_never_carries_an_issue_key():
    for key in ("AB-12", "PROJ-9", "X1-3"):
        branch = cu.branch_for(key, "context-update/")
        assert extract_jira_key(branch) is None, branch


def test_the_body_says_when_to_merge_and_lists_every_change():
    p = cu.propose(_sources(), [_ch("Press Me", "Tap Me"), _ch("Ghost", "Spirit")],
                   {"pages/p.py": "# Press Me here\n"})
    body = cu.render_body("AB-9", p)
    assert "Merge only after the change is deployed" in body
    assert body.count("| `") == len(p.findings)
    assert "pages/p.py:1" in body and "Ghost" in body


# ── wiring ──────────────────────────────────────────────────────────

class _Host:
    def __init__(self, exists=False, fail=False):
        self.exists, self.fail = exists, fail
        self.files, self.deleted, self.prs = {}, [], []

    def branch_exists(self, b):
        return self.exists

    def create_branch(self, b, base="main"):
        self.branch = b

    def create_or_update_file(self, path, content, msg, branch):
        if self.fail:
            raise RuntimeError("push refused")
        self.files[path] = content

    def open_pull_request(self, title, body, head, base="main"):
        self.prs.append((title, head))
        return "https://host.example/pr/1"

    def delete_branch(self, b):
        self.deleted.append(b)
        return True


def _tracker(comments=()):
    t = MagicMock()
    t.get_comments.return_value = list(comments)
    t.get_story.return_value = {"summary": "Rename", "description": "Press Me becomes Tap Me"}
    return t


def _llm(*pairs):
    llm = MagicMock()
    llm.invoke_structured.return_value = WordingChanges(changes=[_ch(o, n) for o, n in pairs])
    return llm


@pytest.fixture
def repo(tmp_path, monkeypatch):
    for rel, text in _sources().items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text, encoding="utf-8")
    monkeypatch.setattr(cu, "context_sources",
                        lambda root: {r: (Path(root) / r).read_text(encoding="utf-8")
                                      for r in _sources()})
    return tmp_path


SETTINGS = {"context_update": {"enabled": True, "branch_prefix": "context-update/"}}


def test_proposes_once_and_comments_with_the_link(repo):
    host, tracker = _Host(), _tracker()
    out = cu.propose_for_story(tracker, host, _llm(("Press Me", "Tap Me")), "AB-9", SETTINGS, repo)
    assert out["context"] == "proposed" and host.prs
    assert set(host.files) == {"inv/app.json", "prompts/app_context/a.md"}
    assert tracker.add_comment.call_args.args[1].startswith(cu.MARKER)
    again = cu.propose_for_story(_tracker([tracker.add_comment.call_args.args[1]]), _Host(),
                                 _llm(("Press Me", "Tap Me")), "AB-9", SETTINGS, repo)
    assert again["context"] == "already-proposed"


def test_nothing_to_change_is_recorded_without_a_pull_request(repo):
    host, tracker = _Host(), _tracker()
    out = cu.propose_for_story(tracker, host, _llm(), "AB-9", SETTINGS, repo)
    assert out["context"] == "none" and not host.prs
    assert "No context update needed" in tracker.add_comment.call_args.args[1]


def test_a_failed_push_removes_the_branch(repo):
    host = _Host(fail=True)
    with pytest.raises(RuntimeError):
        cu.propose_for_story(_tracker(), host, _llm(("Press Me", "Tap Me")), "AB-9", SETTINGS, repo)
    assert host.deleted and not host.prs


def test_disabled_does_nothing(repo):
    llm = _llm(("Press Me", "Tap Me"))
    out = cu.propose_for_story(_tracker(), _Host(), llm,
                               "AB-9", {"context_update": {"enabled": False}}, repo)
    assert out["context"] == "disabled" and not llm.invoke_structured.called


def test_agent0_proposes_after_a_hand_over_and_never_undoes_it(monkeypatch, tmp_path):
    import agents.agent0_impact as a0
    import core.impact_handover as ho
    tracker = MagicMock()
    tracker.find_stories_to_process.return_value = [{"key": "AB-9"}]
    monkeypatch.setattr(ho, "decisions_from_review", lambda t, k, s: ("AB-50", {"AB-12": "approve"}))
    monkeypatch.setattr(ho, "handover", lambda *a, **k: None)
    calls = []

    def boom(*a, **k):
        calls.append(a[3])
        raise RuntimeError("host down")
    monkeypatch.setattr(cu, "propose_for_story", boom)
    settings = {"labels": {"proposed": "impact-proposed"},
                "context_update": {"enabled": True}}
    out = a0.hand_over_decided(tracker, settings, host=object(), llm=object(), root=tmp_path)
    assert calls == ["AB-9"]
    assert out[0]["action"] == "handed-over" and out[0]["context"] == "error"


@pytest.mark.parametrize("action,proposed", [("nothing-to-review", True), ("review-created", False),
                                             ("shadow-report", False), ("dry-run", False)])
def test_agent0_proposes_only_when_the_story_goes_straight_to_ai_ready(monkeypatch, tmp_path,
                                                                       action, proposed):
    import agents.agent0_impact as a0
    tracker = MagicMock()
    tracker.get_story.return_value = {"summary": "s", "description": "d"}
    monkeypatch.setattr(a0, "_already_analysed", lambda *a, **k: False)
    monkeypatch.setattr(a0, "analyse_requirement", lambda *a, **k: {})
    monkeypatch.setattr(a0, "publish", lambda *a, **k: {"story": "AB-9", "action": action})
    calls = []
    monkeypatch.setattr(cu, "propose_for_story",
                        lambda *a, **k: calls.append(a[3]) or {"context": "proposed", "url": "u"})
    out = a0.analyse_and_publish(tracker, "AB-9", object(), {"context_update": {"enabled": True}},
                                 tmp_path, host=object())
    assert (calls == ["AB-9"]) is proposed
    assert (out.get("context") == "proposed") is proposed
