"""Page objects resolve selectors from the app inventory, not from literals.

The inventory is the single source of truth. Two reasons this matters more
than the usual DRY argument:

1. Agent 2 CANNOT hallucinate a selector it never writes. `self.sel("x")` is
   checkable against the inventory; a literal `"input[name='x']"` is not.
2. A selector fixed in the inventory takes effect everywhere at once, with no
   second edit and no chance of two copies disagreeing.
"""
import re
from pathlib import Path

import pytest

from pages.base_page import BasePage
from pages.dashboard_page import DashboardPage
from pages.login_page import LoginPage

PAGES_DIR = Path(__file__).resolve().parents[2] / "pages"
PAGE_OBJECTS = [LoginPage, DashboardPage]

# A selector-looking literal: css, role=, text=, label=, placeholder=, etc.
_SELECTOR_LITERAL = re.compile(
    r'=\s*"(?:'
    r'\s*[.#\[]'                      # .class  #id  [attr=...]
    r'|(?:role|text|label|alt|title|placeholder)='   # playwright engines
    r')[^"]*"'
)


def test_no_page_object_contains_a_selector_literal():
    """The rule this whole change exists to enforce."""
    offenders = []
    for f in sorted(PAGES_DIR.glob("*_page.py")):
        if f.name == "base_page.py":
            continue
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if line.strip().startswith("#") or line.strip().startswith('"'):
                continue
            if _SELECTOR_LITERAL.search(line):
                offenders.append(f"{f.name}:{i}: {line.strip()[:70]}")
    assert not offenders, (
        "selector literal(s) in a page object — use self.sel(\"<key>\") and add "
        "the element to the app inventory:\n  " + "\n  ".join(offenders))


@pytest.mark.parametrize("cls", PAGE_OBJECTS, ids=lambda c: c.__name__)
def test_every_page_object_declares_its_inventory_page(cls):
    assert cls.INVENTORY_PAGE, f"{cls.__name__} must set INVENTORY_PAGE"
    assert cls.INVENTORY_PAGE in (cls._inventory().get("pages") or {}), (
        f"{cls.__name__}.INVENTORY_PAGE = {cls.INVENTORY_PAGE!r} is not in the "
        f"app inventory")


@pytest.mark.parametrize("cls", PAGE_OBJECTS, ids=lambda c: c.__name__)
def test_every_sel_key_used_exists_in_the_inventory(cls):
    """A typo'd key must fail here, not at runtime in a browser."""
    src = (PAGES_DIR / f"{cls.__name__[:-4].lower()}_page.py")
    if not src.is_file():                       # LoginPage -> login_page.py
        src = next(p for p in PAGES_DIR.glob("*_page.py")
                   if f"class {cls.__name__}" in p.read_text(encoding="utf-8"))
    # AST, not regex: a docstring showing `self.sel("<element_key>")` as an
    # EXAMPLE is documentation, not a call, and must not be checked.
    import ast
    tree = ast.parse(src.read_text(encoding="utf-8"))
    keys = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "sel"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)):
            keys.add(node.args[0].value)
    assert keys, f"{cls.__name__} resolves no selectors — is it wired up?"
    for k in sorted(keys):
        cls.sel(k)                              # raises KeyError if unknown


def test_unknown_key_raises_and_lists_what_is_available():
    """A silent None would mis-select; the error must be actionable."""
    with pytest.raises(KeyError) as exc:
        LoginPage.sel("no_such_element")
    msg = str(exc.value)
    assert "no_such_element" in msg
    assert "Available" in msg
    assert "username_input" in msg              # names real keys


def test_page_object_without_inventory_page_fails_clearly():
    class Unwired(BasePage):
        pass
    with pytest.raises(RuntimeError, match="INVENTORY_PAGE"):
        Unwired.sel("anything")


def test_page_url_comes_from_the_inventory():
    assert LoginPage.page_url() == "/web/index.php/auth/login"
    assert DashboardPage.page_url() == "/web/index.php/dashboard/index"