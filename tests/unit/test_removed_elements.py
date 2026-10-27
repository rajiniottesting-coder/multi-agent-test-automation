"""F-11: an element a change story removes is DECLARED removed in the inventory.

Before it, the hand-over only prefixed the element's note `REMOVED by KEY:`
and left the key - it must stay: the story's absence test finds what must be
gone through it. After deployment the nightly checks then reported the
missing element as stale every night, the drift job raised the absence test
as "affected" although missing was now the expected state, and the key was
never cleaned up once no test needed it.

Now the hand-over adds the key to the page's `removed` list. Every reader
treats it as declared gone: missing is expected, present again is drift, and
the nightly inventory update deletes the key once no code names it.

Generic pages and keys only; no application names.
"""
import json
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from core import context_update as cu
from core import inventory_update as iu
from core.impact_analysis import drift_seeds
from core.schemas import NoteRewrites, WordingChanges
from inventory_tools import introspect

SELS = {"badge": "#badge", "save": "#save", "help": "#help"}


# ── the crawler and the health check ────────────────────────────────────

def test_a_removed_element_that_is_gone_is_not_drift():
    diff = introspect.diff_page("p", SELS, {"#badge": 0, "#save": 1, "#help": 1}, set(),
                                declared_removed={"badge"})
    assert diff["missing"] == [] and diff["reappeared"] == []
    assert introspect.summarize_drift({"p": diff}, [])["has_drift"] is False


def test_a_removed_element_on_the_page_again_is_drift_not_ambiguity():
    diff = introspect.diff_page("p", SELS, {"#badge": 2, "#save": 1, "#help": 1}, set(),
                                declared_removed={"badge"})
    assert diff["reappeared"] == [{"element": "badge", "selector": "#badge", "matches": 2}]
    assert diff["ambiguous"] == [] and diff["missing"] == []
    report = introspect.summarize_drift({"p": diff}, [])
    assert report["has_drift"] is True and report["reappeared_selectors"] == 1


def test_without_the_declaration_a_missing_element_is_still_stale():
    diff = introspect.diff_page("p", SELS, {"#badge": 0, "#save": 1, "#help": 1}, set())
    assert diff["missing"] == [{"element": "badge", "selector": "#badge"}]


def test_the_staleness_check_passes_the_declaration(monkeypatch, tmp_path, capsys):
    import sys
    from scripts import check_inventory_staleness as chk
    inv = {"app_name": "X", "pages": {"p": {"url": "/p", "removed": ["badge"],
                                            "elements": dict(SELS)}}}
    path = tmp_path / "inv.json"
    path.write_text(json.dumps(inv))
    monkeypatch.setattr(chk.AppContext, "load", staticmethod(lambda: SimpleNamespace(
        name="X", base_url="https://x.test", inventory_path=lambda: path)))

    @contextmanager
    def browser(headless=True):
        page = MagicMock()
        page.url = "https://x.test/p"
        yield page
    monkeypatch.setattr(chk, "browser_page", browser)
    counts = {"#badge": 1, "#save": 1, "#help": 1}
    monkeypatch.setattr(chk, "resolve_selectors",
                        lambda page, url, sels, attrs: (counts, set(), True))
    out = tmp_path / "r.json"
    monkeypatch.setattr(sys, "argv", ["chk", "--no-login", "--json", str(out)])
    chk.main()
    report = json.loads(out.read_text())
    assert report["pages"]["p"]["reappeared"][0]["element"] == "badge"
    assert "BACK    badge" in capsys.readouterr().out


@pytest.mark.parametrize("count, status, ok", [(0, "GONE", True), (1, "BACK(1)", False)])
def test_verify_locators_reads_a_removed_element(monkeypatch, capsys, count, status, ok):
    from scripts import verify_locators as vl
    counts = {"#badge": count, "#save": 1, "#help": 1}
    monkeypatch.setattr(vl, "_resolve_one", lambda page, sel: SimpleNamespace(
        count=lambda: counts[sel]))
    monkeypatch.setattr(vl, "_wait_for_render", lambda page, sels, *a, **k: True)
    entry = {"url": "/p", "removed": ["badge"], "elements": dict(SELS)}
    good, bad = vl._verify_page(MagicMock(), "https://x.test", "p", entry, 0, False)
    assert status in capsys.readouterr().out
    assert (good, bad) == ((3, 0) if ok else (2, 1))


def test_agent0_seeds_a_removed_element_only_when_it_is_back():
    gone = {"pages": {"p": {"missing": [], "ambiguous": [], "reappeared": []}}}
    back = {"pages": {"p": {"missing": [], "ambiguous": [],
                            "reappeared": [{"element": "badge", "selector": "#badge"}]}}}
    assert drift_seeds(gone).elements == set()
    assert drift_seeds(back).elements == {("p", "badge")}


def test_promote_draft_prunes_a_removed_entry_whose_element_is_gone():
    from scripts.promote_draft import prune
    inv = {"pages": {"p": {"elements": {"save": "#save"}, "removed": ["badge"]}}}
    prune(inv)
    assert "removed" not in inv["pages"]["p"]


# ── the nightly inventory update ────────────────────────────────────────

def _inventory():
    return {"pages": {"p": {"url": "/p", "removed": ["badge"], "multi_match": ["badge"],
                            "elements_notes": {"badge": "REMOVED by AB-9: no badge any more"},
                            "elements": dict(SELS)}}}


def _drift(reappeared=()):
    return {"pages_checked": 1, "pages": {"p": {"missing": [], "ambiguous": [],
                                                "new_data_tests": [],
                                                "reappeared": list(reappeared)}}}


def test_a_removed_key_no_code_names_is_retired_with_every_reference():
    upd = iu.build_update(_drift(), _inventory(), {"save", "help"})
    page = upd.inventory["pages"]["p"]
    assert upd.retired == [{"page": "p", "element": "badge", "selector": "#badge"}]
    assert "badge" not in page["elements"] and "badge" not in page["elements_notes"]
    assert "removed" not in page and page["multi_match"] == []
    assert upd.changed


@pytest.mark.parametrize("why, kwargs, drift", [
    ("a test still asserts it is gone", {"used": {"badge"}}, _drift()),
    ("it is back on the page", {}, _drift([{"element": "badge", "selector": "#badge",
                                            "matches": 1}])),
    ("open pull requests unreadable", {"allow_removal": False}, _drift()),
])
def test_a_removed_key_is_kept_while(why, kwargs, drift):
    used = kwargs.pop("used", set())
    upd = iu.build_update(drift, _inventory(), used, **kwargs)
    assert not upd.retired, why
    assert upd.inventory["pages"]["p"]["removed"] == ["badge"]


def test_a_removed_key_that_is_the_row_family_is_never_retired():
    inv = _inventory()
    inv["pages"]["p"]["row_family"] = "badge"
    upd = iu.build_update(_drift(), inv, set())
    assert not upd.retired and upd.inventory["pages"]["p"]["row_family"] == "badge"


def test_a_removed_key_on_an_unmeasured_or_held_page_is_never_retired():
    unmeasured = {"pages_checked": 1, "pages": {}}
    assert not iu.build_update(unmeasured, _inventory(), set()).retired
    held = _drift()
    held["pages"]["p"]["missing"] = [{"element": "save", "selector": "#save"},
                                     {"element": "help", "selector": "#help"}]
    upd = iu.build_update(held, _inventory(), set(), hold_ratio=0.5)
    assert upd.held_pages and not upd.retired


def test_the_body_lists_retired_and_reappeared_elements():
    upd = iu.build_update(_drift(), _inventory(), set())
    assert "Removed - declared gone, and no test uses them any more" in \
        iu.render_body(upd, "inv.json", "abcdef123456")
    back = iu.build_update(_drift([{"element": "badge", "selector": "#badge", "matches": 2}]),
                           _inventory(), set())
    body = iu.render_body(back, "inv.json", "abcdef123456")
    assert "Declared removed, but on the page again" in body and "`p.badge`" in body


# ── the hand-over declares it ───────────────────────────────────────────

INV = {"pages": {"detail": {"components": ["Detail"], "elements": {"pop": "text=Added",
                                                                   "close": "#close"},
                            "elements_notes": {"pop": "A pop-up confirms the add."}},
                 "other": {"components": ["Other"], "elements": {"x": "#x"}}}}


def _sources(trailing_newline=True):
    text = json.dumps(INV, indent=2, ensure_ascii=False) + ("\n" if trailing_newline else "")
    return {"inv/app.json": text}


def test_the_model_is_shown_element_keys_never_selectors():
    block = cu._notes_block(_sources(), {"detail"})
    assert "- detail: close, pop" in block
    assert "text=Added" not in block and "#close" not in block
    assert "- other:" not in block, "only the pages the story's Components select"


@pytest.mark.parametrize("trailing", [True, False])
def test_a_removed_element_is_declared_keeping_the_files_format(trailing):
    prop = cu.propose(_sources(trailing), [], None, [], None, ["detail.pop"], {"detail"})
    text = prop.edits["inv/app.json"]
    assert json.loads(text)["pages"]["detail"]["removed"] == ["pop"]
    assert text.endswith("\n") is trailing
    assert prop.declared_removed == ["detail.pop"]
    assert "declared `removed` in the inventory" in cu.render_body("AB-9", prop)


def test_an_unusable_removal_reference_is_dropped_with_its_reason():
    prop = cu.propose(_sources(), [], None, [], None,
                      ["pop", "other.x", "detail.nothing", "detail.close", "detail.close"],
                      {"detail"})
    assert [why for _r, _n, why in prop.dropped] == [
        "not written as page.key", "not a page the story's Components select",
        "no such element in the inventory"]
    assert prop.declared_removed == ["detail.close"], "declared once"


def test_an_element_already_declared_is_not_declared_twice():
    inv = json.loads(_sources()["inv/app.json"])
    inv["pages"]["detail"]["removed"] = ["pop"]
    prop = cu.propose({"inv/app.json": json.dumps(inv, indent=2) + "\n"}, [], None, [], None,
                      ["detail.pop"], {"detail"})
    assert prop.empty and not prop.declared_removed


def test_the_hand_over_declares_what_the_model_reports(tmp_path, monkeypatch):
    monkeypatch.setattr(cu, "context_sources", lambda root: _sources())

    def answer(system_prompt="", user_prompt="", output_schema=None):
        if output_schema is NoteRewrites:
            return NoteRewrites(rewrites=[], removed=["detail.pop"])
        return WordingChanges(changes=[])
    llm = MagicMock()
    llm.invoke_structured.side_effect = answer
    tracker = MagicMock()
    tracker.get_comments.return_value = []
    tracker.get_story.return_value = {"summary": "No pop-up", "description": "AC1: removed",
                                      "components": ["Detail"]}
    host = MagicMock()
    host.branch_exists.return_value = False
    host.open_pull_request.return_value = "https://host.example/pr/3"
    out = cu.propose_for_story(tracker, host, llm, "AB-9",
                               {"context_update": {"enabled": True}}, tmp_path)
    assert out["context"] == "proposed"
    written = host.create_or_update_file.call_args.args[1]
    assert json.loads(written)["pages"]["detail"]["removed"] == ["pop"]
