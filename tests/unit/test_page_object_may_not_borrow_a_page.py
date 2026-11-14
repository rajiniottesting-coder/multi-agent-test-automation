"""A new page object may not borrow another page object's inventory page: it
is refused, and the borrowed page is reported as the missing page it is.
"""

from __future__ import annotations

import pytest


def _po(path, cls, page, body="    def open_it(self, base_url: str) -> None:\n        self.navigate(base_url)\n"):
    from types import SimpleNamespace as NS
    return NS(file_path=path, content=(f"from pages.base_page import BasePage\n\n\nclass {cls}(BasePage):\n"
                                       f'    INVENTORY_PAGE = "{page}"\n\n' + body))


@pytest.fixture
def menu_project(tmp_path):
    (tmp_path / "pages").mkdir()
    (tmp_path / "pages" / "menu_page.py").write_text(
        'from pages.base_page import BasePage\n\n\nclass MenuPage(BasePage):\n    INVENTORY_PAGE = "menu"\n')
    return tmp_path, {"pages": {"menu": {"elements": {"reports_link": "a.r"}}}}


def test_a_new_page_object_borrowing_a_page_it_does_not_use_is_refused(menu_project):
    """4 Nov 2026, PRJ-292: the page was not in the inventory; the new page
    object set INVENTORY_PAGE to the navigation entry and navigated by a
    hard-coded path, so the missing page was never named."""
    from validators.method_resolution_validator import validate_page_object_selectors
    root, inv = menu_project
    (err,) = validate_page_object_selectors([_po("pages/reports_page.py", "ReportsPage", "menu")], root, inv)
    assert "MenuPage (pages/menu_page.py) implements, and resolves none of its elements" in err
    using = "    def open_reports(self) -> None:\n        self.click(self.sel(\"reports_link\"))\n"
    # Using the page's elements does not make it this class's page: a page has
    # one page object (E132, 10 Nov 2026).
    (err,) = validate_page_object_selectors(
        [_po("pages/reports_page.py", "ReportsPage", "menu", using)], root, inv)
    assert "is a new page object for INVENTORY_PAGE = 'menu', which MenuPage" in err
    assert validate_page_object_selectors(
        [_po("pages/menu_page.py", "MenuPage", "menu")], root, inv) == []    # its own file


def test_a_borrowed_page_is_reported_as_a_missing_page():
    from core.blocked import blocked_comment
    err = ("Selector inventory error in 'pages/reports_page.py': class ReportsPage sets "
           "INVENTORY_PAGE = 'menu', the page MenuPage (pages/menu_page.py) implements, and "
           "resolves none of its elements. A page object ...")
    text = blocked_comment("AB-1", "0" * 16, [err])
    assert "A new page object (ReportsPage) has no inventory page of its own" in text
    assert "plan_inventory page" in text and "cannot show" not in text
