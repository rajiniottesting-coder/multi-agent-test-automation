"""check_inventory_staleness --compare (design E1): the wiring in main().

--compare adds a `new_elements` section and prints it, but never changes
has_drift or the exit code - an uncovered element is information, not drift.
The browser is faked: no network, no Chromium. The inventory is a small
generic one written to a temporary path, so the tests name no application.
"""
import json
import sys
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import scripts.check_inventory_staleness as chk
from inventory_tools import introspect

BASE = "https://app.example"
INVENTORY = {
    "app_name": "Sample",
    "pages": {
        "home": {"url": "/", "elements": {"save": "[data-qa='save-btn']"}},
    },
}


@pytest.fixture
def run(tmp_path, monkeypatch):
    inv_path = tmp_path / "inventory.json"
    inv_path.write_text(json.dumps(INVENTORY), encoding="utf-8")
    ctx = SimpleNamespace(name="Sample", base_url=BASE,
                          inventory_path=lambda: inv_path)
    monkeypatch.setattr(chk.AppContext, "load", staticmethod(lambda: ctx))

    @contextmanager
    def fake_browser(headless=True):
        page = MagicMock()
        page.url = BASE + "/"
        yield page

    monkeypatch.setattr(chk, "browser_page", fake_browser)
    # The selector is present (count 1) and nothing is missing.
    monkeypatch.setattr(chk, "resolve_selectors",
                        lambda page, url, sels, attrs: ({s: 1 for s in sels}, set(), True))
    descriptors = [{"tag": "button", "attrs": {"id": "cancel"}, "text": "Cancel",
                    "renderedText": "Cancel", "label": "", "visible": True,
                    "thirdParty": False, "hasIconChild": False, "cssPath": ""}]
    monkeypatch.setattr(chk, "collect_uncovered",
                        lambda page, url, sels, attrs: ("Home", descriptors))

    def _run(*flags):
        monkeypatch.setattr(sys, "argv", ["check", "--no-login", *flags])
        return chk.main()
    return _run


def test_compare_reports_uncovered_elements(run, tmp_path, capsys):
    out_json = tmp_path / "report.json"
    code = run("--compare", "--json", str(out_json))
    report = json.loads(out_json.read_text(encoding="utf-8"))
    assert code == 0
    assert "new_elements" in report
    assert report["new_elements"]["home"], "the uncovered button must be reported"
    assert "uncovered elements" in capsys.readouterr().out


def test_compare_never_changes_drift(run, tmp_path):
    base = tmp_path / "base.json"
    cmp_ = tmp_path / "cmp.json"
    run("--json", str(base))
    run("--compare", "--json", str(cmp_))
    a = json.loads(base.read_text(encoding="utf-8"))
    b = json.loads(cmp_.read_text(encoding="utf-8"))
    assert a["has_drift"] is b["has_drift"] is False
    assert "new_elements" not in a and "new_elements" in b


def test_compare_with_fail_on_drift_still_exits_zero(run):
    assert run("--compare", "--fail-on-drift") == 0


def test_without_compare_no_collection_runs(run, monkeypatch):
    called = []
    monkeypatch.setattr(chk, "collect_uncovered",
                        lambda *a, **k: called.append(1) or ("", []))
    run()
    assert called == []


def test_compare_marks_always_page_selectors_on_every_page(run, tmp_path, monkeypatch):
    """A global menu or banner (an `always` page) appears on every page. Its
    elements are covered there too, so its selectors must be marked on each
    page; otherwise every one is reported as uncovered, page after page."""
    inv = {"pages": {
        "home": {"url": "/", "elements": {"save": "[data-qa='save-btn']"}},
        "menu": {"url": "(overlay)", "always": True,
                 "elements": {"menu_home_link": "a.menu-home", "_note": "not a selector"}},
    }}
    (tmp_path / "inventory.json").write_text(json.dumps(inv), encoding="utf-8")
    seen = []

    def capture(page, url, sels, attrs):
        seen.append(list(sels))
        return "Home", []

    monkeypatch.setattr(chk, "collect_uncovered", capture)
    run("--compare")
    assert seen == [["[data-qa='save-btn']", "a.menu-home"]]
