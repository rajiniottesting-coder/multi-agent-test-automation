"""The same words on several pages: a notes change reaches only the page the
story is about.

Three ways the notes went wrong when one text sat in several places:
  * a change story's wording replacement ("Send" -> "Submit") was applied to
    every notes module and every inventory value, selectors on pages the story
    never touched included;
  * a story with no Component had every module offered for its new facts and
    none could be started for its own page - they went into another page's
    module (4 Nov 2026);
  * a new fact was dropped as "already stated" when ANOTHER page's module said
    the same words - a module that stories on this page never read.

Generic modules, pages and stories only; no application names.
"""
import json

import pytest

from core import context_update as cu
from core.schemas import NoteAddition, WordingChange

CORE = "prompts/app_context/core.md"
FORMS = "prompts/app_context/forms.md"
ORDERS = "prompts/app_context/orders.md"
INV = {"pages": {
    "menu": {"always": True, "elements": {"help": "text=Send"}},
    "form": {"components": ["Forms"], "elements": {"send": "text=Send"},
             "elements_notes": {"send": "Send posts the form."}},
    "order": {"components": ["Orders"], "elements": {"send": "text=Send"}},
}}


def _sources(inv=INV):
    return {"inv/app.json": json.dumps(inv, indent=2) + "\n",
            CORE: "# Core\n\nEvery page has a menu.\n",
            FORMS: "# Forms\n\nThe Send button posts the form.\n",
            ORDERS: "# Orders\n\nPress Send to place the order.\n"}


def _change(old="Send", new="Submit"):
    return [WordingChange(old=old, new=new)]


def _sends(text):
    return {k for k, v in json.loads(text)["pages"].items() if v["elements"].get("send") == "text=Submit"}


# ── the wording replacement follows the story's Components ──────────────

def test_a_story_on_one_page_changes_that_page_only():
    src = _sources()
    p = cu.propose(src, _change(), offered={CORE, FORMS}, pages={"menu", "form"}, narrowed=True)
    assert _sends(p.edits["inv/app.json"]) == {"form"}
    assert ORDERS not in p.edits and "Submit button posts" in p.edits[FORMS]
    assert json.loads(p.edits["inv/app.json"])["pages"]["menu"]["elements"]["help"] == "text=Submit"
    outside = {o["where"] for o in p.outside}
    assert outside == {ORDERS, "inv/app.json page order"}
    assert "not changed" in cu.render_body("AB-1", p) and "page order" in cu.render_body("AB-1", p)


def test_text_found_only_outside_the_components_is_not_changed():
    p = cu.propose(_sources(), _change("Press Send", "Press Submit"),
                   offered={CORE, FORMS}, pages={"menu", "form"}, narrowed=True)
    assert p.empty and "found only outside the story's Components" in p.dropped[0][2]


def test_without_a_component_text_on_several_pages_is_listed_not_changed():
    src = _sources()
    p = cu.propose(src, _change(), offered=set(src), pages=set(INV["pages"]), narrowed=False)
    assert p.empty
    why = p.dropped[0][2]
    assert "no Component to say which" in why and "page form" in why and "page order" in why


def test_without_a_component_text_in_one_part_is_changed():
    src = _sources()
    p = cu.propose(src, _change("posts the form", "sends the form"),
                   offered=set(src), pages=set(INV["pages"]), narrowed=False)
    assert set(p.edits) == {"inv/app.json", FORMS}, "one page and its module: one part"


def test_a_caller_without_a_story_replaces_everywhere_as_before():
    p = cu.propose(_sources(), _change())
    assert _sends(p.edits["inv/app.json"]) == {"form", "order"} and ORDERS in p.edits


def test_narrowed_is_read_from_what_the_components_selected(tmp_path):
    src = _sources()
    assert cu._narrowed(src, {CORE, FORMS, "inv/app.json"}, {"menu", "form"}) is True
    assert cu._narrowed(src, set(src), set(INV["pages"])) is False


def test_the_story_wiring_passes_narrowed():
    import inspect
    body = inspect.getsource(cu.propose_for_story)
    assert "narrowed=_narrowed(sources, offered, pages)" in body


# ── additions: a story with no Component, and repeats ───────────────────

FEATURE = "Feature: Feedback\n\n  # JIRA: AB-21 (hash: 1111aaaa) owner: AB-20\n  Scenario: x\n    Given y\n"
STEPS = ('from pytest_bdd import given\n\n\n@given("y")\n'
         'def y(menu_page, form_page, base_url):\n    form_page.open(base_url)\n')
PAGES = {"menu_page.py": 'class MenuPage:\n    INVENTORY_PAGE = "menu"\n',
         "form_page.py": 'class FormPage:\n    INVENTORY_PAGE: str = "form"\n',
         "order_page.py": 'class OrderPage:\n    INVENTORY_PAGE = "order"\n'}


@pytest.fixture
def project(tmp_path):
    (tmp_path / "features").mkdir()
    (tmp_path / "features" / "feedback.feature").write_text(FEATURE)
    (tmp_path / "tests" / "step_defs").mkdir(parents=True)
    (tmp_path / "tests" / "step_defs" / "test_feedback.py").write_text(STEPS)
    (tmp_path / "pages").mkdir()
    for name, text in PAGES.items():
        (tmp_path / "pages" / name).write_text(text)
    return tmp_path


def test_the_components_come_from_the_pages_the_tests_use(project):
    comps, pages = cu.components_from_tests(project, ["AB-21"], INV)
    assert comps == ["Forms"] and pages == ["form"], "the menu (always) is left out"
    assert cu.components_from_tests(project, ["AB-99"], INV) == ([], [])


def test_a_story_with_no_component_gets_its_pages_modules(project, monkeypatch):
    from types import SimpleNamespace
    (project / "prompts" / "app_context").mkdir(parents=True)
    for rel, text in _sources().items():
        if rel.endswith(".md"):
            (project / rel).write_text(text)
    monkeypatch.setattr(cu, "context_sources", lambda root: _sources())
    seen = {}

    def additions(llm, story, key, cases, scenarios, offered, pages, new_modules):
        seen["offered"], seen["new"] = set(offered), dict(new_modules)
        return [NoteAddition(path=FORMS, heading="", text="## Feedback\n\n- Feedback needs a name.",
                             reason="AC1")]
    monkeypatch.setattr(cu, "extract_note_additions", additions)
    tracker = SimpleNamespace(get_story=lambda k: {"summary": "Feedback", "description": "d",
                                                   "components": []},
                              get_linked_test_cases=lambda k: [{"key": "AB-21", "summary": "s"}],
                              get_comments=lambda k: [], add_comment=lambda *a: None)
    host = SimpleNamespace(branch_exists=lambda b: False)
    out = cu.propose_addition_for_story(tracker, host, None, "AB-20",
                                        {"context_update": {"enabled": True}}, project, dry_run=True)
    assert {p for p in seen["offered"] if p.endswith(".md")} == {CORE, FORMS}
    assert out["files"] == [FORMS]
    assert "has no Component; its merged tests use the inventory pages form" in out["body"]


def test_a_fact_another_pages_module_states_is_still_added():
    res = cu.propose_additions(_sources(), [NoteAddition(
        path=FORMS, heading="", text="- Press Send to place the order.", reason="AC2")],
        {CORE, FORMS}, {})
    assert res.added and not res.repeated, "orders.md is not read with forms.md"


def test_a_fact_the_target_or_core_states_is_still_dropped():
    for line in ("- The Send button posts the form.", "- Every page has a menu."):
        res = cu.propose_additions(_sources(), [NoteAddition(path=FORMS, heading="", text=line,
                                                             reason="AC")], {CORE, FORMS}, {})
        assert res.empty and res.repeated
