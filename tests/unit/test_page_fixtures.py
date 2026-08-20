"""Tests for auto-registered page-object fixtures.

conftest.py creates one fixture per page-object class, named after the class in
snake_case. These tests pin the naming convention, the guarantee that explicit
fixtures are never overwritten, and the matching derivation in the validator -
the two must agree or a fixture that works at runtime gets reported as missing.
"""
import re
from pathlib import Path

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


# ── helpers: ask the project, never name this application's pages ────────

_PROJECT = Path(__file__).resolve().parents[2]


def _explicit_conftest_fixtures() -> set:
    """Fixture names conftest declares BY HAND, read from its source.

    Auto-registered fixtures are injected into the same module namespace, so a
    runtime scan cannot tell the two apart.
    """
    import ast
    src = (_PROJECT / "tests" / "step_defs" / "conftest.py").read_text(encoding="utf-8")
    return {
        node.name
        for node in ast.walk(ast.parse(src))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and any("fixture" in ast.dump(d) for d in node.decorator_list)
    }


def _available_page_fixtures() -> set:
    """Every page fixture this project actually offers, however registered."""
    return (_auto_registered_page_fixtures(PROJECT_ROOT)
            | {n for n in _explicit_conftest_fixtures() if n.endswith("_page")})


# ── validator derivation ─────────────────────────────────────────────────

def test_validator_derives_names_from_page_classes():
    """Every page class on disk yields a fixture named in snake_case.

    Asserts the RULE against whatever pages/ holds, rather than naming this
    application's pages: those files are Agent 2's output, so a hardcoded name
    makes a framework test fail whenever a page is deleted or regenerated - and
    stops it running against another app entirely.
    """
    import ast
    names = _auto_registered_page_fixtures(PROJECT_ROOT)

    expected = set()
    for f in (_PROJECT / "pages").glob("*_page.py"):
        if f.name == "base_page.py":
            continue
        for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ClassDef) and node.name.endswith("Page"):
                expected.add(_snake(node.name))

    assert expected, "pages/ holds no page objects - the test is vacuous"
    assert expected <= names | _explicit_conftest_fixtures(), (
        f"page class(es) with no fixture: {sorted(expected - names)}"
    )


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
        f"def go({', '.join(sorted(_available_page_fixtures())[:2])}) -> None:\n"
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
    auto = set(getattr(conftest, "AUTO_REGISTERED_PAGE_FIXTURES", []))

    # Ask conftest what it declares rather than naming this application's
    # pages. A hardcoded list makes a FRAMEWORK test fail the moment a page
    # object is deleted or regenerated - which is Agent 2's job - and it can
    # never run against a different app.
    #
    # Read the SOURCE, not the module namespace: auto-registered fixtures are
    # injected into that same namespace at import, so a runtime scan cannot
    # tell them from the hand-written ones and every fixture looks like both.
    import ast
    source = Path(conftest.__file__).read_text(encoding="utf-8")
    declared = {
        node.name
        for node in ast.walk(ast.parse(source))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and any("fixture" in ast.dump(d) for d in node.decorator_list)
    }
    assert declared, "conftest declares no fixtures at all - the test is vacuous"

    overlap = declared & auto
    assert not overlap, (
        f"{sorted(overlap)} declared by hand AND auto-registered. Auto-"
        f"registration only fills gaps: a hand-written fixture may carry setup "
        f"the generated one would silently drop."
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
    """The registered fixture must construct the class it was derived from.

    Built from a LOCAL class rather than imported from this application's
    pages/: the factory's behaviour has nothing to do with which app is under
    test, and importing a real page object made a framework test fail the
    moment that file was renamed or replaced during an app migration.
    """
    import tests.step_defs.conftest as conftest
    from pages.base_page import BasePage

    class SomeWidgetPage(BasePage):
        INVENTORY_PAGE = "some_widget"

        def __init__(self, page):
            self.page = page

    fixture = conftest._make_page_fixture(SomeWidgetPage)
    assert hasattr(fixture, "_pytestfixturefunction")
    instance = fixture.__wrapped__(page="<stand-in>")
    assert isinstance(instance, SomeWidgetPage)
    assert fixture.__wrapped__.__doc__
    assert "SomeWidgetPage" in fixture.__wrapped__.__doc__

# =========================================================================
# THE SHARED CONFTEST MUST NOT IMPORT ONE APPLICATION'S PAGE OBJECTS
#
# It imported two by name and wrapped each in a fixture the auto-registration
# factory below already produced, identically. The imports bought nothing and
# cost the framework its portability: point config.yaml at another
# application, replace the page objects, and collection dies with
# ModuleNotFoundError at the top of a SHARED conftest before one test runs.
#
# The golden rule's own acceptance test - swap the app, run the suite, it
# passes - did not pass. Nothing checked, because every check ran against the
# one application whose page objects happened to be on disk.
#
# `pages.base_page` is exempt: it is the framework's own class, and the
# factory needs it to recognise a page object at all.
# =========================================================================

def test_the_shared_conftest_imports_no_application_page_object():
    import ast

    source = (_PROJECT / "tests" / "step_defs" / "conftest.py").read_text(
        encoding="utf-8")

    offenders = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("pages."):
            if node.module == "pages.base_page":
                continue
            offenders.append(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("pages.") and alias.name != "pages.base_page":
                    offenders.append(alias.name)

    assert not offenders, (
        f"tests/step_defs/conftest.py imports {offenders}. A shared conftest "
        f"naming one application's page objects cannot be pointed at another "
        f"application - collection fails before any test runs. Page-object "
        f"fixtures are auto-registered from pages/*.py; delete the import and "
        f"the hand-written fixture with it."
    )


def test_every_page_object_on_disk_gets_a_fixture_without_being_named():
    """The other half. Removing the hand-written fixtures is only safe if the
    factory really does cover everything, whatever the application is."""
    import tests.step_defs.conftest as conftest

    auto = set(getattr(conftest, "AUTO_REGISTERED_PAGE_FIXTURES", []))
    on_disk = _auto_registered_page_fixtures(PROJECT_ROOT)

    assert on_disk, "no page objects found on disk - the check would be vacuous"
    missing = on_disk - auto
    assert not missing, (
        f"{sorted(missing)} exist as page objects but have no fixture. The "
        f"factory is the only thing registering them now, so a gap here is a "
        f"gap everywhere."
    )