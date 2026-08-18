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
from pages.nav_page import NavPage


# === Page objects ===

@pytest.fixture
def login_page(page):
    return LoginPage(page)


@pytest.fixture
def nav_page(page):
    """Top navigation. Present on every page, so any scenario that moves
    between areas of the site needs this. Its Logout link is also the
    readiness signal for "am I authenticated"."""
    return NavPage(page)


# === Credentials ===

def _configured_roles() -> str:
    """Role names the environment currently defines, for error messages.

    Read from APP_USER_* at call time rather than hard-coded, so the message
    can never drift from the app under test the way a literal list does.
    Blank-valued variables are ignored: CI exports an empty string for a
    secret that was never set, and reporting that as an available role would
    send someone hunting for a credential that does not exist.
    """
    prefix = "APP_USER_"
    roles = sorted(
        name[len(prefix):].lower()
        for name, value in os.environ.items()
        if name.startswith(prefix) and len(name) > len(prefix) and value.strip()
    )
    return ", ".join(roles) if roles else "(none - no APP_USER_* variable is set)"


@pytest.fixture(scope="session")
def run_id():
    """Short identifier unique to this test run.

    The application under test is a SHARED demo: other users and scheduled
    resets mutate its data at any time. An assertion like 'searching for
    username X returns no records' is only deterministic when X could not
    have been created by anyone else - i.e. when the test derives X from
    this run's own identity. Fixed literal test data on shared state is the
    root cause of flaky zero-result and duplicate-record failures.
    """
    import time, uuid
    return f"{int(time.time())%100000}{uuid.uuid4().hex[:4]}"


@pytest.fixture
def unique_username(run_id, request):
    """A username owned exclusively by the current test.

    Derived from run_id plus the test's own name, so the same run never
    collides with itself either. Any 'record exists' / 'no records' check
    against this name is deterministic on shared data by construction -
    nothing is suppressed or retried to make it pass.
    """
    test_part = "".join(c for c in request.node.name if c.isalnum())[:8]
    return f"tt{run_id}{test_part}"


@pytest.fixture(scope="session")
def credentials():
    """Resolve a role name to (username, password) from the environment.

    The lookup is derived from the role's own name, so no role is named here:

        role "<name>"  ->  username  APP_USER_<NAME>
                       ->  password  APP_PASSWORD_<NAME>, else APP_PASSWORD

    Whichever APP_USER_* variables the environment defines ARE the roles this
    suite has. That is what keeps this shared file application-agnostic:
    onboarding a different app means editing .env and the CI secrets, never
    this fixture.
    """
    def _for(role: str) -> tuple[str, str]:
        key = role.strip().upper().replace("-", "_").replace(" ", "_")
        if not key:
            # An empty role reaches here when a feature file writes
            # 'I log in as ""' or the step regex captured nothing. Say that,
            # rather than reporting a missing APP_USER_ variable that no one
            # was ever meant to set.
            raise RuntimeError(
                "Empty login role. The scenario must name a role, e.g. "
                "'When I log in as a \"admin\" user'."
            )
        user = os.getenv(f"APP_USER_{key}")
        if not user:
            raise RuntimeError(
                f"No credential configured for login role '{role}'. Roles are "
                f"LOGIN IDENTITIES - not pages, not Jira components. "
                f"Configured right now: {_configured_roles()}. If '{role}' is a "
                f"real role, set APP_USER_{key} in .env (local) or GitHub "
                f"Secrets (CI). If it is not a role, fix the feature file "
                f"instead."
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
#     LoginPage           ->  login_page
#     SearchResultsPage   ->  search_results_page
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
    """SearchResultsPage -> search_results_page."""
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