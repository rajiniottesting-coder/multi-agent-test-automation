"""F-8: when a story's pull request merges, the facts its feature adds reach the notes.

Before it, the context update could only REPLACE wording and REWRITE passages a
change story made untrue: it never added. A new feature - or a change story
adding a rule - never reached the app notes, and the next story on that
feature was drafted from its own text alone. Now the Story Done on merge
workflow proposes the addition as a reviewed pull request: facts only, into
the story's Component modules (a new module for a new Component), and every
line the notes already state is dropped deterministically.

Generic modules, stories and pages only; no application names.
"""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import yaml

from core import context_update as cu
from core.schemas import NoteAddition, NoteAdditions

ROOT = Path(__file__).resolve().parents[2]
CORE = "prompts/app_context/core.md"
BASKET = "prompts/app_context/basket.md"
WISH = "prompts/app_context/wishlist.md"
INV = {"pages": {"basket": {"components": ["Basket"], "elements": {"pay": "#pay"},
                            "elements_notes": {"pay": "Paying needs an address."}},
                 "profile": {"components": ["Profile"], "elements": {"save": "#save"},
                             "elements_notes": {"save": "Saving shows a toast."}}}}
NOTES = {
    "core.md": "# Core\n\nShared accounts keep their state between runs.\n",
    "basket.md": "# Basket\n\n## Paying\n\n- Paying needs an address.\n\n## Coupons\n\n"
                 "One coupon per order.\n",
    "profile.md": "# Profile\n\nThe profile keeps one address.\n",
}
FEATURE = """Feature: Basket coupons

  # JIRA: AB-11 (hash: 1234abcd) owner: AB-5
  Scenario: A second coupon is refused
    Given a basket with a coupon applied
    When I apply a second coupon
    Then I should see "Only one coupon per order"

  # JIRA: AB-99 (hash: 9999abcd) owner: AB-1
  Scenario: Another story's scenario
    Given something else
"""


def _add(path, text, heading="", reason="AC1"):
    return NoteAddition(path=path, heading=heading, text=text, reason=reason)


def _sources():
    return {f"prompts/app_context/{n}": t for n, t in NOTES.items()} | {
        "inv/app.json": json.dumps(INV, indent=2) + "\n"}


OFFERED = {CORE, BASKET, "inv/app.json"}


# ── near-duplicates ─────────────────────────────────────────────────────

@pytest.mark.parametrize("line, dup", [
    ("- Paying needs an address.", True),                  # same line
    ("An address is needed for paying", False),             # other words
    ("- needs an address paying", True),                    # same words, reordered
    ("Paying needs an address", True),                      # contained
    ("- A paid order cannot be changed.", False),
    ("- ...", True),                                        # no words at all
])
def test_near_duplicate(line, dup):
    assert cu.near_duplicate(line, cu._units(NOTES["basket.md"])) is dup


# ── placing an addition ─────────────────────────────────────────────────

def test_an_addition_under_a_heading_continues_its_list():
    res = cu.propose_additions(_sources(), [_add(BASKET, "- A paid order cannot be changed.",
                                                 "Paying")], OFFERED, {})
    text = res.edits[BASKET]
    assert "- Paying needs an address.\n- A paid order cannot be changed.\n\n## Coupons" in text
    assert text.endswith("One coupon per order.\n")


def test_a_paragraph_under_the_last_heading_and_a_new_section_at_the_end():
    res = cu.propose_additions(_sources(), [
        _add(BASKET, "A coupon expires after seven days.", "Coupons"),
        _add(BASKET, "## Gift wrap\n\n- Gift wrap is offered at checkout.")], OFFERED, {})
    text = res.edits[BASKET]
    assert text.endswith("One coupon per order.\n\nA coupon expires after seven days.\n\n"
                         "## Gift wrap\n\n- Gift wrap is offered at checkout.\n")


def test_an_unknown_heading_becomes_a_new_section():
    res = cu.propose_additions(_sources(), [_add(BASKET, "- Points are earned per order.",
                                                 "Loyalty points")], OFFERED, {})
    assert res.edits[BASKET].endswith("## Loyalty points\n\n- Points are earned per order.\n")


def test_a_new_component_gets_its_own_module():
    res = cu.propose_additions(_sources(), [_add(WISH, "- A wishlist holds at most 10 items.")],
                               OFFERED, {WISH: "Wishlist"})
    assert res.edits[WISH] == "# Wishlist\n\n- A wishlist holds at most 10 items.\n"
    assert res.added[0]["new_file"] is True


def test_what_is_refused_and_why():
    res = cu.propose_additions(_sources(), [
        _add("prompts/app_context/profile.md", "- Profiles keep three addresses."),
        _add("inv/app.json", "- a note"),
        _add(BASKET, "   "),
        _add(BASKET, "- " + "x " * 900),
        _add("prompts/app_context/other.md", "- anything")], OFFERED, {}, max_chars=1500)
    reasons = [why for _p, _s, why in res.dropped]
    assert reasons == ["not a notes module the story's Components select",
                       "not a notes module the story's Components select",
                       "empty addition", "longer than 1500 characters",
                       "not a notes module the story's Components select"]
    assert res.empty


def test_lines_the_notes_already_state_are_dropped_and_the_rest_kept():
    res = cu.propose_additions(_sources(), [_add(BASKET, "- Paying needs an address.\n"
                                                         "- A paid order cannot be changed.",
                                                 "Paying")], OFFERED, {})
    assert res.repeated == [(BASKET, "- Paying needs an address.")]
    assert res.added[0]["text"] == "- A paid order cannot be changed."


def test_an_addition_the_notes_fully_hold_is_dropped():
    res = cu.propose_additions(_sources(), [_add(BASKET, "One coupon per order.", "Coupons"),
                                            _add(CORE, "- Shared accounts keep their state "
                                                       "between runs.")], OFFERED, {})
    assert res.empty and [w for *_x, w in res.dropped] == ["the notes already state it"] * 2


def test_a_later_addition_is_checked_against_an_earlier_one():
    res = cu.propose_additions(_sources(), [_add(BASKET, "- Gift wrap is free.", "Coupons"),
                                            _add(CORE, "- Gift wrap is free.")], OFFERED, {})
    assert len(res.added) == 1 and res.repeated == [(CORE, "- Gift wrap is free.")]


def test_the_sources_are_never_modified():
    sources = _sources()
    before = dict(sources)
    cu.propose_additions(sources, [_add(BASKET, "- New fact here.")], OFFERED, {})
    assert sources == before


def test_new_module_paths_only_for_components_without_a_module(tmp_path):
    folder = tmp_path / "prompts" / "app_context"
    folder.mkdir(parents=True)
    (folder / "basket.md").write_text("x")
    assert cu.new_module_paths(["Basket", "Gift Cards", "gift-cards", ""], tmp_path) == {
        "prompts/app_context/gift_cards.md": "gift-cards"}
    assert cu.new_module_paths(["Basket"], tmp_path / "nowhere") == {}


# ── reading the merged story ────────────────────────────────────────────

def test_story_scenarios_are_found_by_their_markers(tmp_path):
    (tmp_path / "features").mkdir()
    (tmp_path / "features" / "basket.feature").write_text(FEATURE)
    text = cu.story_scenarios(tmp_path, ["ab-11"])
    assert "A second coupon is refused" in text and "Only one coupon per order" in text
    assert "Another story's scenario" not in text


def _llm(additions, seen=None):
    def answer(system_prompt="", user_prompt="", output_schema=None):
        assert output_schema is NoteAdditions
        if seen is not None:
            seen["prompt"] = user_prompt
        return NoteAdditions(additions=additions)
    llm = MagicMock()
    llm.invoke_structured.side_effect = answer
    return llm


@pytest.fixture
def repo(tmp_path, monkeypatch):
    folder = tmp_path / "prompts" / "app_context"
    folder.mkdir(parents=True)
    for name, text in NOTES.items():
        (folder / name).write_text(text, encoding="utf-8")
    (tmp_path / "features").mkdir()
    (tmp_path / "features" / "basket.feature").write_text(FEATURE)
    (tmp_path / "inv").mkdir()
    (tmp_path / "inv" / "app.json").write_text(json.dumps(INV, indent=2) + "\n")
    monkeypatch.setattr(cu, "context_sources",
                        lambda root: {"inv/app.json": (Path(root) / "inv/app.json").read_text()}
                        | {f"prompts/app_context/{n}": (folder / n).read_text() for n in NOTES})
    return tmp_path


SETTINGS = {"context_update": {"enabled": True, "branch_prefix": "context-update/",
                               "additions": True, "max_addition_chars": 1500}}


def _tracker(components=("Basket", "Wishlist"), comments=()):
    t = MagicMock()
    t.get_comments.return_value = list(comments)
    t.get_story.return_value = {"summary": "One coupon per order",
                                "description": "AC1: a second coupon is refused",
                                "components": list(components)}
    t.get_linked_test_cases.return_value = [
        {"key": "AB-11", "summary": "[Negative] A second coupon is refused",
         "description": "Expected: 'Only one coupon per order'"}]
    return t


class _Host:
    def __init__(self, existing=()):
        self.branches, self.files, self.prs = set(existing), {}, []
    def branch_exists(self, b): return b in self.branches
    def create_branch(self, b, base="main"): self.branches.add(b)
    def create_or_update_file(self, path, content, msg, branch): self.files[path] = content
    def open_pull_request(self, title, body, head, base="main"):
        self.prs.append((title, body, head))
        return "https://host.example/pr/5"
    def delete_branch(self, b): return True


def test_the_prompt_holds_the_story_its_cases_scenarios_and_only_its_notes(repo):
    seen = {}
    cu.propose_addition_for_story(_tracker(), _Host(), _llm([], seen), "AB-5", SETTINGS, repo)
    p = seen["prompt"]
    assert "Story AB-5" in p and "AC1: a second coupon is refused" in p
    assert "AB-11: [Negative] A second coupon is refused" in p
    assert 'Then I should see "Only one coupon per order"' in p
    assert "prompts/app_context/wishlist.md (Component: Wishlist)" in p
    assert "One coupon per order." in p and "Paying needs an address." in p
    assert "The profile keeps one address." not in p and "Saving shows a toast." not in p
    assert "#pay" not in p, "never a selector"


def test_a_merged_story_gets_one_notes_pull_request(repo):
    host, tracker = _Host(), _tracker()
    out = cu.propose_addition_for_story(tracker, host, _llm([
        _add(BASKET, "- A second coupon is refused with \"Only one coupon per order\".",
             "Coupons"),
        _add(WISH, "- A wishlist holds at most 10 items.")]), "AB-5", SETTINGS, repo)
    assert out == {"story": "AB-5", "addition": "proposed", "url": "https://host.example/pr/5"}
    title, body, head = host.prs[0]
    assert head == "context-update/ab-5-notes"
    from config import extract_jira_key
    assert extract_jira_key(head) is None, "merging it must not close or report on the story"
    assert set(host.files) == {BASKET, WISH}
    assert "a new module" in body and "under `Coupons`" in body
    assert tracker.add_comment.call_args.args[1].startswith(cu.ADD_MARKER)


def test_nothing_new_is_said_once_on_the_story(repo):
    tracker = _tracker()
    out = cu.propose_addition_for_story(tracker, _Host(), _llm([
        _add(BASKET, "One coupon per order.", "Coupons")]), "AB-5", SETTINGS, repo)
    assert out["addition"] == "none"
    assert "No notes addition needed" in tracker.add_comment.call_args.args[1]


def test_a_story_already_handled_costs_no_model_call(repo):
    llm = _llm([])
    host = _Host(existing={"context-update/ab-5-notes"})
    assert cu.propose_addition_for_story(_tracker(), host, llm, "AB-5", SETTINGS,
                                         repo)["addition"] == "already-proposed"
    story_hash = cu._story_hash(_tracker().get_story())
    marked = _tracker(comments=[f"{cu.ADD_MARKER} No notes addition needed\n(story: {story_hash})"])
    assert cu.propose_addition_for_story(marked, _Host(), llm, "AB-5", SETTINGS,
                                         repo)["addition"] == "already-proposed"
    assert llm.invoke_structured.call_count == 0


def test_an_edited_story_is_checked_again(repo):
    old = _tracker(comments=[f"{cu.ADD_MARKER} No notes addition needed\n(story: deadbeef0000)"])
    out = cu.propose_addition_for_story(old, _Host(), _llm([]), "AB-5", SETTINGS, repo)
    assert out["addition"] == "none"


@pytest.mark.parametrize("cfg", [{"enabled": False, "additions": True},
                                 {"enabled": True, "additions": False}])
def test_switched_off_does_nothing(repo, cfg):
    llm = _llm([])
    out = cu.propose_addition_for_story(_tracker(), _Host(), llm, "AB-5",
                                        {"context_update": cfg}, repo)
    assert out["addition"] == "disabled" and llm.invoke_structured.call_count == 0


def test_a_dry_run_returns_the_body_and_writes_nothing(repo):
    host, tracker = _Host(), _tracker()
    out = cu.propose_addition_for_story(tracker, host, _llm([
        _add(WISH, "- A wishlist holds at most 10 items.")]), "AB-5", SETTINGS, repo,
        dry_run=True)
    assert out["addition"] == "dry-run" and out["files"] == [WISH]
    assert "A wishlist holds at most 10 items." in out["body"]
    assert not host.prs and not host.files and not tracker.add_comment.called


# ── the script and the workflow ─────────────────────────────────────────

def test_a_branch_without_a_story_key_proposes_nothing(capsys):
    from scripts import propose_context_addition as script
    assert script.main(["--branch", "framework/new-docs"]) == 0
    assert "not a story pull request" in capsys.readouterr().out


@pytest.mark.parametrize("settings", [
    {"enabled": False, "context_update": {"enabled": True, "additions": True}},
    {"enabled": True, "context_update": {"enabled": True, "additions": False}},
])
def test_the_script_respects_the_switches(monkeypatch, capsys, settings):
    from scripts import propose_context_addition as script
    monkeypatch.setattr(script, "impact_settings", lambda: settings)
    assert script.main(["--story", "AB-5"]) == 0
    assert "nothing proposed" in capsys.readouterr().out


def test_shadow_mode_prints_and_posts_cost(monkeypatch, capsys):
    from scripts import propose_context_addition as script
    monkeypatch.setattr(script, "impact_settings", lambda: {
        "enabled": True, "shadow_mode": True, **SETTINGS})
    calls = {}

    def fake(tracker, host, llm, key, settings, root, dry_run=False):
        calls["dry_run"] = dry_run
        return {"addition": "dry-run", "files": [WISH], "body": "BODY"}
    monkeypatch.setattr(cu, "propose_addition_for_story", fake)
    monkeypatch.setattr("integrations.tracker.get_tracker", lambda: MagicMock())
    monkeypatch.setattr("integrations.repo_host.get_repo_host", lambda: MagicMock())
    monkeypatch.setattr("core.llm_client.LLMClient", lambda **k: MagicMock())
    assert script.main(["--branch", "auto/AB-5-coupons"]) == 0
    assert calls["dry_run"] is True and "Agent 0 shadow mode: nothing written" in capsys.readouterr().out


def test_a_live_run_posts_its_cost_to_the_story(monkeypatch, capsys):
    from scripts import propose_context_addition as script
    monkeypatch.setattr(script, "impact_settings", lambda: {"enabled": True, **SETTINGS})
    monkeypatch.setattr(cu, "propose_addition_for_story",
                        lambda *a, **k: {"addition": "proposed", "url": "u"})
    tracker = MagicMock()
    monkeypatch.setattr("integrations.tracker.get_tracker", lambda: tracker)
    monkeypatch.setattr("integrations.repo_host.get_repo_host", lambda: MagicMock())
    monkeypatch.setattr("core.llm_client.LLMClient", lambda **k: MagicMock())
    monkeypatch.setattr("core.llm_client.get_usage_summary", lambda: {"llm_calls": 1})
    posted = {}
    monkeypatch.setattr("core.usage_ledger.post_usage_to_story",
                        lambda key, agent, usage, jira=None: posted.update(key=key, agent=agent))
    assert script.main(["--story", "ab-5"]) == 0
    assert posted == {"key": "AB-5", "agent": "Agent 0 (Impact Analyst)"}


def test_the_merge_workflow_proposes_the_notes_after_done():
    wf = yaml.safe_load((ROOT / ".github/workflows/story_done_on_merge.yml").read_text())
    steps = wf["jobs"]["mark-done"]["steps"]
    names = [s.get("name") for s in steps]
    i = names.index("Propose the notes the story adds")
    assert i > names.index("Move story to Done")
    step = steps[i]
    assert "scripts.propose_context_addition --branch" in step["run"]
    assert step["env"]["GITHUB_TOKEN"] == "${{ secrets.GH_PAT }}"
    assert "OPENAI_API_KEY" in step["env"] and "JIRA_API_TOKEN" in step["env"]
    assert "$BRANCH" in step["run"], "the branch reaches the script through the environment"
