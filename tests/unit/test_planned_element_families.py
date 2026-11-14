"""A planned list of like elements can be declared a family (multi-match) in
the inventory, and a declared family with several matches is confirmed.
"""

from __future__ import annotations


def _inv():
    return {"pages": {"p": {"url": "/p", "elements": {"head": "h1"}}}}


def test_a_planned_family_is_declared_multi_match():
    from core.inventory_planned import add_planned_element, add_planned_page
    out, why = add_planned_element(_inv(), "p", "rows", "ul > li", family=True)
    assert not why and out["pages"]["p"]["multi_match"] == ["rows"]
    out, why = add_planned_element(_inv(), "p", "one", "#one")
    assert not why and "multi_match" not in out["pages"]["p"]
    out, why = add_planned_page(_inv(), "q", "/q", {"items": ".item", "title": "h2"},
                                ["Q"], families=["items"])
    assert not why and out["pages"]["q"]["multi_match"] == ["items"]
    _out, why = add_planned_page(_inv(), "q", "/q", {"title": "h2"}, ["Q"], families=["nope"])
    assert "--family names no element" in why


def test_a_declared_planned_family_with_several_matches_is_confirmed():
    from inventory_tools.introspect import diff_page
    d = diff_page("p", {"rows": "ul > li"}, {"ul > li": 27}, set(), [],
                  declared_family={"rows"}, declared_planned={"rows"})
    assert [x["element"] for x in d["planned_live"]] == ["rows"] and not d["ambiguous"]
    d = diff_page("p", {"rows": "ul > li"}, {"ul > li": 27}, set(), [],
                  declared_planned={"rows"})
    assert not d["planned_live"] and d["ambiguous"], "undeclared: ambiguous, never confirmed"


def test_the_script_takes_family():
    from scripts.plan_inventory import main
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        assert main(["page", "--page", "zz_demo", "--url", "/zz_demo", "--component", "Z",
                     "--element", "rows=ul > li", "--family", "rows", "--dry-run"]) == 0
    assert '"multi_match": [\n    "rows"' in buf.getvalue()
