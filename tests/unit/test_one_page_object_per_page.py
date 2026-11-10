"""E132: a page has one page object.

A story needing one more method on a reserved page object got a second, new
page object for the same inventory page instead. A new class for a page a
committed page object implements is refused; it names that page object, and
says so when it is reserved. Generic pages and keys only.
"""
import json
import textwrap
from pathlib import Path
from types import SimpleNamespace

import pytest

from validators import method_resolution_validator as mrv
from validators.method_resolution_validator import validate_page_object_selectors


def _root(tmp_path: Path) -> Path:
    (tmp_path / "app_inventory").mkdir()
    (tmp_path / "config").mkdir()
    (tmp_path / "pages").mkdir()
    (tmp_path / "app_inventory" / "app.json").write_text(json.dumps({
        "app_name": "Test App",
        "pages": {"menu": {"url": "/", "always": True,
                           "elements": {"help_link": "#help", "start_link": "#home"}},
                  "listing": {"url": "/listing", "elements": {"grid": "#grid"}}},
    }), encoding="utf-8")
    (tmp_path / "config" / "config.yaml").write_text(
        "app_under_test:\n  name: Test App\n  inventory_file: app_inventory/app.json\n",
        encoding="utf-8")
    (tmp_path / "pages" / "menu_page.py").write_text(textwrap.dedent('''
        from pages.base_page import BasePage
        class MenuPage(BasePage):
            INVENTORY_PAGE = "menu"
            def go_start(self) -> None:
                self.click(self.sel("start_link"))
    '''), encoding="utf-8")
    return tmp_path


def _new(path, cls, page, key):
    return SimpleNamespace(file_path=path, content=textwrap.dedent(f'''
        from pages.base_page import BasePage
        class {cls}(BasePage):
            INVENTORY_PAGE = "{page}"
            def open_help(self) -> None:
                self.click(self.sel("{key}"))
    '''))


@pytest.mark.parametrize("reserved", [False, True])
def test_a_second_page_object_for_a_page_is_refused(tmp_path, monkeypatch, reserved):
    root = _root(tmp_path)
    monkeypatch.setattr(mrv, "_reserved_page_files",
                        lambda: {"pages/menu_page.py"} if reserved else set())
    (err,) = [e for e in validate_page_object_selectors(
        [_new("pages/help_menu_page.py", "HelpMenuPage", "menu", "help_link")], root)
        if "already implements" in e]
    assert "class HelpMenuPage is a new page object for INVENTORY_PAGE = 'menu'" in err
    assert "MenuPage (pages/menu_page.py) already implements" in err
    if reserved:
        assert "RESERVED" in err and "a person adds it there" in err
    else:
        assert "add the methods to MenuPage in pages/menu_page.py" in err


def test_extending_the_page_object_itself_or_a_new_page_passes(tmp_path):
    root = _root(tmp_path)
    same = _new("pages/menu_page.py", "MenuPage", "menu", "help_link")
    other = _new("pages/listing_page.py", "ListingPage", "listing", "grid")
    assert not [e for e in validate_page_object_selectors([same, other], root)
                if "already implements" in e]
