"""Fixtures shared by all step-definition modules.

Only fixtures belong here. Step definitions are declared in each step-def
module, not in this file.

`page` and `base_url` are inherited from tests/conftest.py.
"""
import importlib
import inspect
import os
import pkgutil
import re

import pytest

import pages as pages_package
from pages.base_page import BasePage
from pages.login_page import LoginPage
from pages.dashboard_page import DashboardPage
from pages.menu_page import MenuPage


# === Page objects ===

@pytest.fixture
def login_page(page):
    return LoginPage(page)


@pytest.fixture
def dashboard_page(page):
    return DashboardPage(page)


@pytest.fixture
def menu_page(page):
    """Sidebar and top bar. Present on every authenticated page, so any
    scenario that navigates between modules needs this."""
    return MenuPage(page)


# === Credentials ===

@pytest.fixture(scope="session")
def credentials():
    """Resolve a role name to (username, password) from the environment.

    For role "standard":
        username -> APP_USER_STANDARD
        password -> APP_PASSWORD_STANDARD, else APP_PASSWORD
    """
    def _for(role: str) -> tuple[str, str]:
        key = role.strip().upper().replace("-", "_").replace(" ", "_")
        user = os.getenv(f"APP_USER_{key}")
        if not user:
            raise RuntimeError(
                f"No credential configured for login role '{role}'. Roles are "
                f"LOGIN IDENTITIES (standard, locked_out, admin) - not pages or "
                f"Jira components. If '{role}' is a real role, set APP_USER_{key} "
                f"in .env (local) or GitHub Secrets (CI). If it is not a role, "
                f"fix the feature file instead."
            )
        password = os.getenv(f"APP_PASSWORD_{key}") or os.getenv("APP_PASSWORD")
        if not password:
            raise RuntimeError(
                f"Missing password for role '{role}'. "
                f"Set APP_PASSWORD_{key} or APP_PASSWORD."
            )
        return user, password

    return _for

# ──────────────────────────────────────────────────────────────────────────
# Auto-registered page-object fixtures
# ──────────────────────────────────────────────────────────────────────────
#
# Every page object gets a fixture named after its class, in snake_case:
#
#     LoginPage      ->  login_page
#     AdminAddUserPage  ->  admin_add_user_page
#
# That convention was already being followed by hand for every fixture above.
# Registering it here means a NEW page object landing in pages/ gets its
# fixture automatically - no conftest edit, and nothing for a code-generating
# agent to write into a file every test depends on.
#
# Fixtures declared explicitly above are NEVER overwritten: this only fills in
# names that do not already exist. So anything needing custom setup stays
# hand-written and keeps working exactly as before.
#
# These are ordinary pytest fixtures, so `pytest --fixtures` still lists them.
# validators/gherkin_analyzer.py derives the same names from the same classes,
# so a step definition requesting one is not reported as missing.

# Fixture names supplied by pytest, pytest-bdd or pytest-playwright. A page
# object deriving one of these must never overwrite it.
_RESERVED_FIXTURE_NAMES = frozenset({
    "page", "context", "browser", "browser_name", "browser_type",
    "playwright", "request", "base_url", "new_context", "launch_browser",
    "monkeypatch", "tmp_path", "capsys", "caplog", "record_property",
})


def _snake_case(name: str) -> str:
    """AdminAddUserPage -> admin_add_user_page."""
    return re.sub(r'(?<!^)(?=[A-Z])', '_', name).lower()


def _make_page_fixture(page_object_class):
    """Build a function-scoped fixture returning an instance of the class."""
    def _page_object_fixture(page):
        return page_object_class(page)
    # Set before decorating, so `pytest --fixtures` shows it.
    _page_object_fixture.__doc__ = (
        f"Auto-registered fixture for {page_object_class.__name__}."
    )
    return pytest.fixture(_page_object_fixture)


def _register_page_object_fixtures() -> list:
    """Create a fixture per page-object class. Returns the names registered.

    Never raises: a page object that fails to import must not take the whole
    suite down at collection time. It is skipped, and the missing fixture
    surfaces as a normal pytest error naming the one file at fault.
    """
    registered = []
    for _, module_name, _ in pkgutil.iter_modules(pages_package.__path__):
        try:
            module = importlib.import_module(f'pages.{module_name}')
        except Exception:
            continue
        for _name, obj in inspect.getmembers(module, inspect.isclass):
            if not issubclass(obj, BasePage) or obj is BasePage:
                continue
            if obj.__module__ != module.__name__:
                continue        # imported into this module, not defined here
            fixture_name = _snake_case(obj.__name__)
            if fixture_name in _RESERVED_FIXTURE_NAMES:
                # A class named Page would derive 'page' and shadow the
                # browser fixture this factory itself depends on -
                # infinite recursion, and every test broken.
                continue
            if fixture_name in globals():
                continue        # explicitly defined above - leave it alone
            globals()[fixture_name] = _make_page_fixture(obj)
            registered.append(fixture_name)
    return registered


AUTO_REGISTERED_PAGE_FIXTURES = _register_page_object_fixtures()