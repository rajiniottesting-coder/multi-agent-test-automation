"""Page objects resolve selectors from the app inventory, not from literals.

APP-AGNOSTIC BY CONSTRUCTION
---------------------------
These tests exercise the MECHANISM (BasePage.sel / page_url and the
no-literals rule), never a particular application. Pointing the framework at a
different app must not change a line here, so:

  - the sel()/page_url() tests build a SYNTHETIC inventory and a throwaway
    page object; they import no application page object and never read the
    real inventory
  - the no-literals scan walks whatever is in pages/ and cares only about the
    SHAPE of what it finds

Why the rule exists: the inventory is the single source of truth, and an agent
cannot hallucinate a selector it never writes. `self.sel("x")` is checkable
against the inventory; a literal `"input[name='x']"` is not.
"""
import ast
import json
import re
from pathlib import Path

import pytest

from pages.base_page import BasePage

PAGES_DIR = Path(__file__).resolve().parents[2] / "pages"

# A selector-looking literal: css, or one of Playwright's engine prefixes.
# A selector literal, wherever it appears. The original pattern required an
# `= "..."`, so it caught an ASSIGNMENT - `SELECTOR = "#id"` - and missed the
# commoner shape by far: the literal handed straight to a helper,
# `self.click("#id")`. One injected into a committed page object passed the
# entire suite. Matching the quoted string itself covers both, and both quote
# styles.
_SELECTOR_LITERAL = re.compile(
    r"""["'](?:\s*[.#\[]|(?:role|text|label|alt|title|placeholder)=)[^"']*["']"""
)


# A synthetic app. Deliberately nothing to do with the app under test.
_FAKE_INVENTORY = {
    "pages": {
        "widget_screen": {
            "url": "/widgets/list",
            "elements": {
                "search_box": "[data-test='search']",
                "submit_button": "role=button[name='Go']",
            },
        }
    }
}


@pytest.fixture
def fake_inventory(monkeypatch):
    """Point BasePage at a synthetic inventory for the duration of a test."""
    monkeypatch.setattr(BasePage, "_INVENTORY_CACHE", _FAKE_INVENTORY,
                        raising=False)
    yield
    monkeypatch.setattr(BasePage, "_INVENTORY_CACHE", None, raising=False)


class _WidgetPage(BasePage):
    INVENTORY_PAGE = "widget_screen"


class _UnwiredPage(BasePage):
    pass


# ── the mechanism ────────────────────────────────────────────

def test_sel_resolves_a_key_to_its_selector(fake_inventory):
    assert _WidgetPage.sel("search_box") == "[data-test='search']"
    assert _WidgetPage.sel("submit_button") == "role=button[name='Go']"


def test_page_url_comes_from_the_inventory(fake_inventory):
    assert _WidgetPage.page_url() == "/widgets/list"


def test_unknown_key_raises_and_lists_what_is_available(fake_inventory):
    """A silent None would mis-select; the error must be actionable."""
    with pytest.raises(KeyError) as exc:
        _WidgetPage.sel("no_such_element")
    msg = str(exc.value)
    assert "no_such_element" in msg
    assert "Available" in msg
    assert "search_box" in msg                    # names the real keys


def test_unknown_inventory_page_raises_and_lists_the_pages(fake_inventory):
    class _Wrong(BasePage):
        INVENTORY_PAGE = "no_such_page"
    with pytest.raises(KeyError, match="Available pages"):
        _Wrong.sel("anything")


def test_page_object_without_inventory_page_fails_clearly(fake_inventory):
    with pytest.raises(RuntimeError, match="INVENTORY_PAGE"):
        _UnwiredPage.sel("anything")
    with pytest.raises(RuntimeError, match="INVENTORY_PAGE"):
        _UnwiredPage.page_url()


# ── the rule, applied to whatever pages/ contains ────────────

def _page_object_files():
    return [f for f in sorted(PAGES_DIR.glob("*_page.py"))
            if f.name != "base_page.py"]


def test_no_page_object_contains_a_selector_literal():
    """The rule this whole design exists to enforce."""
    offenders = []
    for f in _page_object_files():
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith(("#", '"', "'", "*")):
                continue
            if _SELECTOR_LITERAL.search(line):
                offenders.append(f"{f.name}:{i}: {stripped[:70]}")
    assert not offenders, (
        'selector literal(s) in a page object — use self.sel("<key>") and add '
        "the element to the app inventory:\n  " + "\n  ".join(offenders))


def test_every_page_object_declares_an_inventory_page():
    """Without it, sel() raises at runtime instead of at import."""
    missing = []
    for f in _page_object_files():
        src = f.read_text(encoding="utf-8")
        if "INVENTORY_PAGE" not in src:
            missing.append(f.name)
    assert not missing, (
        f"page object(s) with no INVENTORY_PAGE: {missing}. Set it to the key "
        f"of the page they implement in the app inventory.")


def test_every_sel_key_used_exists_in_the_real_inventory():
    """Whatever app is configured, every key a page object asks for must be in
    its inventory page. AST, not regex: a docstring showing self.sel("<key>")
    as an EXAMPLE is documentation, not a call."""
    cfg = (PAGES_DIR.parent / "config" / "config.yaml").read_text(encoding="utf-8")
    m = re.search(r'inventory_file:\s*"([^"]+)"', cfg)
    if not m:
        pytest.skip("no inventory_file configured")
    inv_path = PAGES_DIR.parent / m.group(1)
    if not inv_path.is_file():
        pytest.skip(f"inventory not present at {inv_path}")
    pages = json.loads(inv_path.read_text(encoding="utf-8")).get("pages") or {}

    problems = []
    for f in _page_object_files():
        src = f.read_text(encoding="utf-8")
        page_key = re.search(r'INVENTORY_PAGE\s*=\s*"([^"]+)"', src)
        if not page_key:
            continue
        page_key = page_key.group(1)
        if page_key not in pages:
            problems.append(f"{f.name}: INVENTORY_PAGE={page_key!r} not in inventory")
            continue
        elements = (pages[page_key].get("elements") or {})
        for node in ast.walk(ast.parse(src)):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "sel"
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)):
                key = node.args[0].value
                if key not in elements:
                    problems.append(
                        f"{f.name}:{node.lineno}: sel({key!r}) not in "
                        f"inventory page {page_key!r}")
    assert not problems, "\n  " + "\n  ".join(problems)

def test_no_page_object_builds_locator_syntax_in_code():
    """Applied to whatever `pages/` contains, not to a fixture.

    The generation gate rejects `f"{self.sel('rows')} >> nth={i}"`, but a gate
    only guards what passes THROUGH it. These files are Agent 2's output and
    they live on disk: a regeneration, a hand-edit, or a merge that predates
    the rule can all reintroduce the pattern without the gate ever running.

    This is the check that makes the fix durable rather than a one-time
    cleanup - it fails the suite on whatever is actually committed.
    """
    offenders = []
    for f in _page_object_files():
        source = f.read_text(encoding="utf-8")
        # Docstrings legitimately SHOW the anti-pattern while teaching it, and
        # base_page.py sets that example. Ask the AST rather than guessing
        # from a line prefix, which only catches a line STARTING with a quote.
        doc_lines = set()
        try:
            for node in ast.walk(ast.parse(source)):
                if (isinstance(node, ast.Expr)
                        and isinstance(node.value, ast.Constant)
                        and isinstance(node.value.value, str)):
                    doc_lines.update(
                        range(node.lineno, (node.end_lineno or node.lineno) + 1))
        except SyntaxError:
            pass

        for i, line in enumerate(source.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith(("#", '"', "'", "*")) or i in doc_lines:
                continue
            if ">> nth=" in line or ">>nth=" in line:
                offenders.append(f"{f.name}:{i}: {stripped[:70]}")

    assert not offenders, (
        "locator syntax built in code — use "
        'self.click_nth(self.sel("<key>"), index), and get the index from '
        "self.find_row_index_by_text(...) so the element is chosen by what it "
        "SAYS before it is reached by where it sits:\n  " + "\n  ".join(offenders))