"""Tests for auto-registered page-object fixtures.

conftest.py creates one fixture per page-object class, named after the class in
snake_case. These tests pin the naming convention, the guarantee that explicit
fixtures are never overwritten, and the matching derivation in the validator -
the two must agree or a fixture that works at runtime gets reported as missing.
"""
import re

import pytest

from validators.gherkin_analyzer import (
    _auto_registered_page_fixtures,
    validate_fixtures_exist,
)
from config.paths import PROJECT_ROOT


class _GF:
    """Minimal stand-in for a GeneratedFile."""

    def __init__(self, file_path: str, content: str):
        self.file_path = file_path
        self.content = content


def _snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


# ── the naming convention ────────────────────────────────────────────────

@pytest.mark.parametrize("class_name,expected", [
    ("LoginPage", "login_page"),
    ("HomePage", "home_page"),
    ("NavPage", "nav_page"),
    ("AdminAddUserPage", "admin_add_user_page"),
    ("PIMPage", "p_i_m_page"),          # documents the acronym edge case
])
def test_snake_case_convention(class_name, expected):
    assert _snake(class_name) == expected


# ── validator derivation ─────────────────────────────────────────────────

def test_validator_derives_names_from_page_classes():
    names = _auto_registered_page_fixtures(PROJECT_ROOT)
    assert "login_page" in names
    assert "home_page" in names
    assert "nav_page" in names


def test_base_page_never_becomes_a_fixture():
    """BasePage is abstract - it is never instantiated directly."""
    assert "base_page" not in _auto_registered_page_fixtures(PROJECT_ROOT)


def test_derivation_is_silent_without_a_project_root():
    assert _auto_registered_page_fixtures(None) == set()


def test_derivation_is_silent_when_pages_dir_is_absent(tmp_path):
    assert _auto_registered_page_fixtures(tmp_path) == set()


def test_new_page_object_needs_no_conftest_edit(tmp_path):
    """The whole point: a page object appearing on disk yields a fixture name."""
    pages = tmp_path / "pages"
    pages.mkdir()
    (pages / "base_page.py").write_text("class BasePage:\n    pass\n", encoding="utf-8")
    (pages / "widget_page.py").write_text(
        "from pages.base_page import BasePage\n\n\n"
        "class WidgetPage(BasePage):\n    pass\n",
        encoding="utf-8",
    )
    assert "widget_page" in _auto_registered_page_fixtures(tmp_path)


# ── the two must agree ───────────────────────────────────────────────────

def test_validator_accepts_an_auto_registered_fixture():
    """A step def requesting a page-object fixture must not be flagged."""
    step_def = (
        "from pytest_bdd import given\n\n\n"
        '@given("I am somewhere")\n'
        "def go(login_page, home_page, nav_page) -> None:\n"
        "    pass\n"
    )
    errors = validate_fixtures_exist(
        [_GF("tests/step_defs/test_x.py", step_def)], PROJECT_ROOT
    )
    assert errors == []


def test_validator_still_catches_a_genuinely_missing_fixture():
    """Auto-registration must not blunt the check it was added alongside."""
    step_def = (
        "from pytest_bdd import given\n\n\n"
        '@given("I am somewhere")\n'
        "def go(no_such_thing) -> None:\n"
        "    pass\n"
    )
    errors = validate_fixtures_exist(
        [_GF("tests/step_defs/test_y.py", step_def)], PROJECT_ROOT
    )
    assert len(errors) == 1
    assert "no_such_thing" in errors[0]


# ── explicit fixtures are sacred ─────────────────────────────────────────

def test_explicitly_declared_fixtures_are_not_overwritten():
    """A hand-written fixture may have custom setup; auto-registration only
    fills gaps, so anything declared by hand must survive untouched."""
    import tests.step_defs.conftest as conftest
    auto = getattr(conftest, "AUTO_REGISTERED_PAGE_FIXTURES", [])
    for explicit in ("login_page", "home_page", "nav_page", "credentials"):
        assert explicit not in auto, (
            f"{explicit} is declared explicitly and must not be auto-registered"
        )


def test_every_page_class_on_disk_is_reachable_as_a_fixture():
    """No page object may be left without a fixture, however it was created."""
    import tests.step_defs.conftest as conftest
    auto = set(getattr(conftest, "AUTO_REGISTERED_PAGE_FIXTURES", []))
    explicit = {
        name for name in dir(conftest)
        if name.endswith("_page") and not name.startswith("_")
    }
    for derived in _auto_registered_page_fixtures(PROJECT_ROOT):
        assert derived in auto or derived in explicit, (
            f"page-object fixture '{derived}' is neither auto-registered "
            f"nor declared explicitly"
        )


# ── negative flows: hostile page-object files ────────────────────────────

def _pages_dir(tmp_path, **files):
    """Build a throwaway pages/ package. Always includes base_page.py."""
    pages = tmp_path / "pages"
    pages.mkdir(exist_ok=True)
    (pages / "base_page.py").write_text("class BasePage:\n    pass\n", encoding="utf-8")
    for name, body in files.items():
        (pages / name).write_text(body, encoding="utf-8")
    return tmp_path


def test_class_shadowing_a_builtin_fixture_is_refused(tmp_path):
    """A class named Page derives 'page' and would shadow the browser fixture.

    The factory itself depends on `page`, so registering it would recurse and
    break every test in the suite.
    """
    root = _pages_dir(tmp_path, page_page=None) if False else _pages_dir(
        tmp_path,
        **{"page.py": "from pages.base_page import BasePage\n\n\n"
                      "class Page(BasePage):\n    pass\n"},
    )
    assert "page" not in _auto_registered_page_fixtures(root)


def test_unparseable_page_file_yields_no_fixture(tmp_path):
    """A file that does not parse cannot be imported, so conftest skips it.

    Claiming its fixture exists would let a genuinely missing fixture through.
    """
    root = _pages_dir(
        tmp_path,
        **{"broken.py": "class Oops(BasePage:\n    not python\n"},
    )
    assert "oops" not in _auto_registered_page_fixtures(root)


def test_class_that_does_not_subclass_base_page_is_ignored(tmp_path):
    root = _pages_dir(
        tmp_path,
        **{"helper.py": "class NotAPage:\n    pass\n"},
    )
    assert "not_a_page" not in _auto_registered_page_fixtures(root)


def test_reimported_class_is_not_double_counted(tmp_path):
    """A page object imported into another module must yield one name, not two."""
    root = _pages_dir(
        tmp_path,
        **{
            "real_page.py": "from pages.base_page import BasePage\n\n\n"
                            "class RealPage(BasePage):\n    pass\n",
            "aggregator.py": "from pages.real_page import RealPage\n",
        },
    )
    assert _auto_registered_page_fixtures(root) == {"real_page"}


def test_unusual_spacing_still_recognised(tmp_path):
    root = _pages_dir(
        tmp_path,
        **{"odd_page.py": "from pages.base_page import BasePage\n\n\n"
                          "class   Odd (BasePage) :\n    pass\n"},
    )
    assert "odd" in _auto_registered_page_fixtures(root)


def test_underscore_prefixed_module_is_skipped(tmp_path):
    root = _pages_dir(
        tmp_path,
        **{"_private_page.py": "from pages.base_page import BasePage\n\n\n"
                               "class PrivatePage(BasePage):\n    pass\n"},
    )
    assert "private_page" not in _auto_registered_page_fixtures(root)


def test_conftest_refuses_reserved_names_too():
    """Both sides must agree: conftest must never register a reserved name."""
    import tests.step_defs.conftest as conftest
    reserved = conftest._RESERVED_FIXTURE_NAMES
    assert "page" in reserved and "browser" in reserved and "request" in reserved
    for name in conftest.AUTO_REGISTERED_PAGE_FIXTURES:
        assert name not in reserved


def test_factory_builds_the_right_class():
    """The registered fixture must construct the class it was derived from."""
    import tests.step_defs.conftest as conftest
    from pages.login_page import LoginPage
    fixture = conftest._make_page_fixture(LoginPage)
    assert hasattr(fixture, "_pytestfixturefunction")
    instance = fixture.__wrapped__(page="<stand-in>")
    assert isinstance(instance, LoginPage)
    assert fixture.__wrapped__.__doc__ and "LoginPage" in fixture.__wrapped__.__doc__