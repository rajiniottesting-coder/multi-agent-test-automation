"""
scripts/verify_locators.py with --inventory: the draft-review path.

`Path` was imported inside main(), after its first use. Python then treats it
as a local name for the whole function, so the sign-in step's
`Path(args.inventory)` raised UnboundLocalError on every run that passed
--inventory with sign-in on - reviewing a draft inventory for a login-gated
app - before a single selector was checked. The default run (no --inventory)
never evaluates that expression, which is why the nightly sweep stayed green.

These run main() for real with the browser faked: no network, no Chromium.
The inventory is the configured one, copied to a temporary path, so the
tests name no application.
"""
import json
import shutil
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import scripts.verify_locators as vl
from core.app_context import AppContext
from inventory_tools.browser import find_login_path


class _Reached(Exception):
    """Raised by a fake once main() has got past the code under test."""


@pytest.fixture
def draft(tmp_path, monkeypatch):
    """A copy of the configured inventory at a path only --inventory names."""
    path = tmp_path / "app.draft.json"
    shutil.copy(AppContext.load().inventory_path(), path)

    @contextmanager
    def fake_browser(headless=True):
        yield MagicMock()

    monkeypatch.setattr(vl, "browser_page", fake_browser)
    return path


def _main(monkeypatch, *argv):
    monkeypatch.setattr(sys, "argv", ["verify_locators", "--headless", *argv])
    return vl.main()


def test_inventory_flag_with_sign_in_reads_the_login_page_from_that_file(draft, monkeypatch):
    seen = {}

    def fake_login(page, login_url, *a):
        seen["login_url"] = login_url
        raise _Reached

    monkeypatch.setattr(vl, "do_login", fake_login)
    with pytest.raises(_Reached):            # UnboundLocalError before the fix
        _main(monkeypatch, "--inventory", str(draft))
    expected = find_login_path(json.loads(draft.read_text(encoding="utf-8"))) or "/"
    assert seen["login_url"].endswith(expected)


def test_single_selector_page_lookup_reads_the_inventory_flag(draft, monkeypatch):
    """The --selector --page path read --inventory through a second, aliased
    function-level import; it now uses the module's Path too."""
    pages = json.loads(draft.read_text(encoding="utf-8"))["pages"]
    key, entry = next((k, v) for k, v in sorted(pages.items())
                      if "<" not in (v.get("url") or "/"))
    seen = {}

    def fake_page_goto(url):
        seen["url"] = url
        raise _Reached

    @contextmanager
    def browser(headless=True):
        page = MagicMock()
        page.goto.side_effect = fake_page_goto
        yield page

    monkeypatch.setattr(vl, "browser_page", browser)
    with pytest.raises(_Reached):
        _main(monkeypatch, "--no-login", "--inventory", str(draft),
              "--selector", "body", "--page", key)
    assert seen["url"].endswith(entry.get("url") or "/")


def test_main_binds_no_module_name_as_a_local():
    """Guard against the same mistake coming back: `Path` (and every other
    module name) is imported at the top now, so a function-level import of it
    inside main() would again make it local there and break earlier uses."""
    code = compile(Path(vl.__file__).read_text(encoding="utf-8"), vl.__file__, "exec")
    main = next(c for c in code.co_consts if getattr(c, "co_name", "") == "main")
    shadowed = set(main.co_varnames) & set(vars(vl))
    assert not shadowed, f"main() shadows module names: {sorted(shadowed)}"
