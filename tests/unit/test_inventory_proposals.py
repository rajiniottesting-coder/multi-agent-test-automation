"""Inventory proposals (E1 follow-up): propose, review, apply.

Pure logic first, then the apply CLI and the --propose wiring. Everything runs
against temporary files with generic names; no browser, no network.
"""
import copy
import json
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from core import inventory_proposals as ip
from scripts import apply_inventory_proposals as cli
from scripts import check_inventory_staleness as chk

INV = {
    "app_name": "Sample",
    "pages": {
        "widgets": {"components": ["Widgets"],
                    "elements": {"save_button": "[data-qa='save']"}},
    },
}


# ─────────────────────────────────────────────────────────────
# Pure: building proposals
# ─────────────────────────────────────────────────────────────

def test_every_row_starts_unapplied_and_unrefused():
    doc = ip.build_proposals({"widgets": {"cancel_button": "#cancel"}}, INV,
                             inventory_path="inv.json")
    (row,) = doc["rows"]
    assert row["apply"] is False and row["refused"] == ""


def test_a_name_already_on_the_page_is_refused_at_propose_time():
    doc = ip.build_proposals({"widgets": {"save_button": "#other"}}, INV,
                             inventory_path="inv.json")
    assert "already exists" in doc["rows"][0]["refused"]


def test_a_selector_already_used_on_the_page_is_refused():
    doc = ip.build_proposals({"widgets": {"new_name": "[data-qa='save']"}}, INV,
                             inventory_path="inv.json")
    assert "already used" in doc["rows"][0]["refused"]


def test_a_page_not_in_the_inventory_is_refused():
    doc = ip.build_proposals({"ghost": {"x_button": "#x"}}, INV, inventory_path="inv.json")
    assert "not in the inventory" in doc["rows"][0]["refused"]


@pytest.mark.parametrize("bad_name", ["CamelCase", "_note", "has space", "", "1st"])
def test_a_name_that_is_not_snake_case_is_refused(bad_name):
    doc = ip.build_proposals({"widgets": {bad_name: "#x"}}, INV, inventory_path="inv.json")
    assert "snake_case" in doc["rows"][0]["refused"]


def test_an_empty_selector_is_refused():
    doc = ip.build_proposals({"widgets": {"cancel_button": "  "}}, INV, inventory_path="inv.json")
    assert "empty" in doc["rows"][0]["refused"]


def test_rows_are_sorted_for_a_stable_review_file():
    doc = ip.build_proposals({"widgets": {"b_button": "#b", "a_button": "#a"}}, INV,
                             inventory_path="inv.json")
    assert [r["element"] for r in doc["rows"]] == ["a_button", "b_button"]


# ─────────────────────────────────────────────────────────────
# Pure: applying proposals
# ─────────────────────────────────────────────────────────────

def _row(**kw):
    base = {"page": "widgets", "element": "cancel_button", "selector": "#cancel",
            "apply": True, "refused": ""}
    base.update(kw)
    return base


def test_only_rows_marked_apply_are_added():
    rows = [_row(), _row(element="other_button", selector="#o", apply=False)]
    out, applied, refused = ip.apply_proposals(INV, rows)
    assert [a["element"] for a in applied] == ["cancel_button"]
    assert "other_button" not in out["pages"]["widgets"]["elements"]
    assert refused == []


def test_apply_does_not_modify_the_input_inventory():
    before = copy.deepcopy(INV)
    ip.apply_proposals(INV, [_row()])
    assert INV == before


def test_a_marked_row_that_conflicts_now_is_refused_with_a_reason():
    out, applied, refused = ip.apply_proposals(INV, [_row(element="save_button")])
    assert applied == []
    assert out["pages"]["widgets"]["elements"]["save_button"] == "[data-qa='save']"
    assert "already exists" in refused[0]["refused"]


def test_a_stale_refusal_note_is_rechecked_against_the_present_inventory():
    """The inventory changed since propose: the name is free now, so it is added."""
    stale = _row(refused="name 'cancel_button' already exists on this page")
    _, applied, refused = ip.apply_proposals(INV, [stale])
    assert [a["element"] for a in applied] == ["cancel_button"] and refused == []


def test_a_row_whose_page_disappeared_is_refused():
    _, applied, refused = ip.apply_proposals(INV, [_row(page="gone")])
    assert applied == [] and "not in the inventory" in refused[0]["refused"]


# ─────────────────────────────────────────────────────────────
# CLI: apply
# ─────────────────────────────────────────────────────────────

@pytest.fixture
def files(tmp_path):
    inv = tmp_path / "inventory.json"
    inv.write_text(json.dumps(INV, indent=2) + "\n", encoding="utf-8")
    proposals = tmp_path / "proposals.json"
    proposals.write_text(json.dumps({
        "schema": ip.PROPOSALS_SCHEMA, "inventory": "inventory.json", "base_url": "",
        "rows": [_row()],
    }), encoding="utf-8")
    return inv, proposals


def test_dry_run_writes_nothing(files):
    inv, proposals = files
    before = inv.read_text(encoding="utf-8")
    assert cli.main([str(proposals), "--inventory", str(inv), "--dry-run"]) == 0
    assert inv.read_text(encoding="utf-8") == before


def test_yes_adds_exactly_the_marked_element_and_changes_nothing_else(files):
    inv, proposals = files
    assert cli.main([str(proposals), "--inventory", str(inv), "--yes"]) == 0
    got = json.loads(inv.read_text(encoding="utf-8"))
    expected = copy.deepcopy(INV)
    expected["pages"]["widgets"]["elements"]["cancel_button"] = "#cancel"
    assert got == expected


def test_without_yes_and_no_terminal_it_refuses_to_write(files, monkeypatch):
    inv, proposals = files
    before = inv.read_text(encoding="utf-8")
    monkeypatch.setattr(sys, "stdin", MagicMock(isatty=lambda: False))
    assert cli.main([str(proposals), "--inventory", str(inv)]) == 1
    assert inv.read_text(encoding="utf-8") == before


def test_an_unknown_schema_is_rejected(files):
    inv, proposals = files
    proposals.write_text(json.dumps({"schema": 99, "rows": []}), encoding="utf-8")
    assert cli.main([str(proposals), "--inventory", str(inv), "--yes"]) == 1


# ─────────────────────────────────────────────────────────────
# Wiring: check_inventory_staleness --propose
# ─────────────────────────────────────────────────────────────

@pytest.fixture
def propose_run(tmp_path, monkeypatch):
    inv_path = tmp_path / "inventory.json"
    inv_path.write_text(json.dumps(INV), encoding="utf-8")
    ctx = SimpleNamespace(name="Sample", base_url="https://app.example",
                          inventory_file="inventory.json", inventory_path=lambda: inv_path)
    monkeypatch.setattr(chk.AppContext, "load", staticmethod(lambda: ctx))

    from contextlib import contextmanager

    @contextmanager
    def fake_browser(headless=True):
        page = MagicMock()
        page.url = "https://app.example/"
        yield page

    monkeypatch.setattr(chk, "browser_page", fake_browser)
    monkeypatch.setattr(chk, "resolve_selectors",
                        lambda page, url, sels, attrs: ({s: 1 for s in sels}, set(), True))
    descriptors = [{"tag": "button", "attrs": {"id": "cancel"}, "text": "Cancel",
                    "renderedText": "Cancel", "label": "", "visible": True,
                    "thirdParty": False, "hasIconChild": False, "cssPath": ""}]
    monkeypatch.setattr(chk, "collect_uncovered",
                        lambda page, url, sels, attrs: ("Widgets", descriptors))

    def _run(*flags):
        monkeypatch.setattr(sys, "argv", ["check", "--no-login", *flags])
        return chk.main()
    return _run, inv_path


def test_propose_writes_a_reviewable_file_and_leaves_the_inventory_alone(propose_run, tmp_path):
    run, inv_path = propose_run
    before = inv_path.read_text(encoding="utf-8")
    out = tmp_path / "proposals.json"
    assert run("--propose", str(out)) == 0
    assert inv_path.read_text(encoding="utf-8") == before
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["schema"] == ip.PROPOSALS_SCHEMA
    assert doc["inventory"] == "inventory.json"
    assert doc["rows"] and all(r["apply"] is False for r in doc["rows"])
    assert doc["rows"][0]["page"] == "widgets"


def test_propose_then_apply_round_trip(propose_run, tmp_path, monkeypatch):
    run, inv_path = propose_run
    out = tmp_path / "proposals.json"
    run("--propose", str(out))
    doc = json.loads(out.read_text(encoding="utf-8"))
    for row in doc["rows"]:
        row["apply"] = True
    out.write_text(json.dumps(doc), encoding="utf-8")
    assert cli.main([str(out), "--inventory", str(inv_path), "--yes"]) == 0
    got = json.loads(inv_path.read_text(encoding="utf-8"))
    row = doc["rows"][0]
    assert got["pages"]["widgets"]["elements"][row["element"]] == row["selector"]
