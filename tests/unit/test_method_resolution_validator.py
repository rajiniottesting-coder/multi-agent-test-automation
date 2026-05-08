"""Unit tests for the method resolution validator (Hotfix v5).

Coverage:
    1. Regression tests for the EXACT bugs from the SCRUM-23 logout run:
        - click_logout_link vs click_logout
        - is_logout_link_in_menu_visible vs is_logout_link_visible
        - are_login_form_fields_visible doesn't exist on LoginPage
    2. Inheritance handling (BasePage methods like is_visible)
    3. In-batch page object resolution
    4. On-disk page object resolution (reserved files)
    5. Naming-convention fallback (inventory_page -> InventoryPage)
    6. False-positive guards (Playwright .page calls, unknown vars, etc.)
    7. Error format compatibility with the repair loop
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from agents.method_resolution_validator import (
    _build_class_source_map,
    _collect_step_def_function_args,
    _extract_method_calls_on_fixtures,
    _find_similar_methods,
    _parse_class_bases,
    _parse_class_methods,
    _parse_fixtures,
    _parse_imports_for_classes,
    _resolve_class_methods_with_inheritance,
    validate_method_resolution,
)
from agents.schemas import GeneratedFile


# Helper: tiny class for building synthetic GeneratedFile objects
def gf(file_path: str, content: str) -> GeneratedFile:
    return GeneratedFile(file_path=file_path, content=content, is_new_file=True, purpose="test")


# Helper: build a project root with a real pages/ dir for on-disk tests
@pytest.fixture
def fake_project(tmp_path: Path) -> Path:
    pages = tmp_path / "pages"
    pages.mkdir()
    (pages / "__init__.py").write_text("")
    # BasePage with common methods
    (pages / "base_page.py").write_text(textwrap.dedent("""
        from playwright.sync_api import Page

        class BasePage:
            def __init__(self, page: Page):
                self.page = page

            def navigate(self, url: str) -> None:
                self.page.goto(url)

            def is_visible(self, locator: str) -> bool:
                return self.page.locator(locator).is_visible()

            def get_title(self) -> str:
                return self.page.title()
    """).strip())
    # LoginPage as a reserved on-disk class
    (pages / "login_page.py").write_text(textwrap.dedent("""
        from pages.base_page import BasePage

        class LoginPage(BasePage):
            USERNAME_INPUT = "[data-test='username']"
            PASSWORD_INPUT = "[data-test='password']"
            LOGIN_BUTTON = "[data-test='login-button']"
            ERROR_MESSAGE = "[data-test='error']"

            def open(self, base_url: str) -> None:
                self.navigate(base_url)

            def login_as(self, username: str, password: str) -> None:
                self.page.fill(self.USERNAME_INPUT, username)
                self.page.fill(self.PASSWORD_INPUT, password)
                self.page.click(self.LOGIN_BUTTON)

            def get_error_message(self) -> str:
                return self.page.locator(self.ERROR_MESSAGE).inner_text()
    """).strip())
    return tmp_path


# =============================================================================
# REGRESSION TESTS — the exact bugs from the SCRUM-23 logout run
# =============================================================================
class TestSCRUM23Regressions:
    """The actual bugs from the run:
        - click_logout() defined, click_logout_link() called
        - is_logout_link_visible() defined, is_logout_link_in_menu_visible() called
        - are_login_form_fields_visible() called on LoginPage but never defined
    """

    def test_click_logout_link_vs_click_logout_caught(self, fake_project: Path):
        # Page object defines click_logout
        page_obj = gf("pages/inventory_page.py", textwrap.dedent("""
            from pages.base_page import BasePage

            class InventoryPage(BasePage):
                BURGER = "[data-test='open-sidebar']"

                def open_burger_menu(self) -> None:
                    self.page.click(self.BURGER)

                def click_logout(self) -> None:
                    self.page.click("[data-test='logout-link']")
        """).strip())

        # Step def calls click_logout_link  (BUG)
        step_def = gf("tests/step_defs/test_logout.py", textwrap.dedent("""
            import pytest
            from pytest_bdd import scenarios, given, when, then
            from pages.inventory_page import InventoryPage

            @pytest.fixture
            def inventory_page(page):
                return InventoryPage(page)

            @when("I click the logout link")
            def click_logout_option(inventory_page):
                inventory_page.click_logout_link()
        """).strip())

        errors = validate_method_resolution([page_obj, step_def], fake_project)
        assert len(errors) == 1
        assert "click_logout_link" in errors[0]
        assert "InventoryPage" in errors[0]
        assert "click_logout" in errors[0]  # suggested fix
        assert "tests/step_defs/test_logout.py" in errors[0]

    def test_is_logout_link_in_menu_visible_caught(self, fake_project: Path):
        page_obj = gf("pages/inventory_page.py", textwrap.dedent("""
            from pages.base_page import BasePage

            class InventoryPage(BasePage):
                LOGOUT_LINK = "[data-test='logout-link']"

                def is_logout_link_visible(self) -> bool:
                    return self.is_visible(self.LOGOUT_LINK)
        """).strip())

        step_def = gf("tests/step_defs/test_logout.py", textwrap.dedent("""
            import pytest
            from pytest_bdd import then
            from pages.inventory_page import InventoryPage

            @pytest.fixture
            def inventory_page(page):
                return InventoryPage(page)

            @then("I should see the logout option")
            def verify_logout_option_visible(inventory_page):
                assert inventory_page.is_logout_link_in_menu_visible()
        """).strip())

        errors = validate_method_resolution([page_obj, step_def], fake_project)
        assert len(errors) == 1
        assert "is_logout_link_in_menu_visible" in errors[0]
        assert "is_logout_link_visible" in errors[0]  # suggested fix

    def test_hallucinated_method_on_reserved_file_caught(self, fake_project: Path):
        # LoginPage is on disk in fake_project — it has open, login_as, get_error_message
        # Step def calls are_login_form_fields_visible which doesn't exist
        step_def = gf("tests/step_defs/test_logout.py", textwrap.dedent("""
            import pytest
            from pytest_bdd import then
            from pages.login_page import LoginPage

            @pytest.fixture
            def login_page(page):
                return LoginPage(page)

            @then("I should see the login form")
            def verify_login_form(login_page):
                assert login_page.are_login_form_fields_visible()
        """).strip())

        errors = validate_method_resolution([step_def], fake_project)
        assert len(errors) == 1
        assert "are_login_form_fields_visible" in errors[0]
        assert "LoginPage" in errors[0]

    def test_all_three_scrum23_bugs_caught_together(self, fake_project: Path):
        """Verify all three bugs from the actual run get flagged in one pass."""
        page_obj = gf("pages/inventory_page.py", textwrap.dedent("""
            from pages.base_page import BasePage

            class InventoryPage(BasePage):
                def open_burger_menu(self) -> None: ...
                def click_logout(self) -> None: ...
                def is_logout_link_visible(self) -> bool: return True
        """).strip())

        step_def = gf("tests/step_defs/test_logout.py", textwrap.dedent("""
            import pytest
            from pytest_bdd import given, when, then
            from pages.inventory_page import InventoryPage
            from pages.login_page import LoginPage

            @pytest.fixture
            def inventory_page(page):
                return InventoryPage(page)

            @pytest.fixture
            def login_page(page):
                return LoginPage(page)

            @when("I click logout")
            def click_logout_option(inventory_page):
                inventory_page.click_logout_link()  # BUG 1

            @then("logout option visible")
            def verify_logout(inventory_page):
                assert inventory_page.is_logout_link_in_menu_visible()  # BUG 2

            @then("login form visible")
            def verify_form(login_page):
                assert login_page.are_login_form_fields_visible()  # BUG 3
        """).strip())

        errors = validate_method_resolution([page_obj, step_def], fake_project)
        assert len(errors) == 3
        # All errors target the same step def file (so repair loop groups them)
        assert all("tests/step_defs/test_logout.py" in e for e in errors)


# =============================================================================
# INHERITANCE — methods from BasePage are valid
# =============================================================================
class TestInheritance:
    def test_basepage_method_called_via_subclass_accepted(self, fake_project: Path):
        page_obj = gf("pages/inventory_page.py", textwrap.dedent("""
            from pages.base_page import BasePage

            class InventoryPage(BasePage):
                CONTAINER = "[data-test='inventory-container']"
        """).strip())

        # is_visible and navigate are inherited from BasePage
        step_def = gf("tests/step_defs/test_inv.py", textwrap.dedent("""
            import pytest
            from pytest_bdd import then
            from pages.inventory_page import InventoryPage

            @pytest.fixture
            def inventory_page(page):
                return InventoryPage(page)

            @then("inventory loaded")
            def verify(inventory_page):
                inventory_page.navigate("https://example.com")
                assert inventory_page.is_visible("[data-test='inventory-container']")
        """).strip())

        errors = validate_method_resolution([page_obj, step_def], fake_project)
        assert errors == []

    def test_three_level_inheritance_chain(self, fake_project: Path, tmp_path: Path):
        # Create an intermediate class
        (fake_project / "pages" / "logged_in_page.py").write_text(textwrap.dedent("""
            from pages.base_page import BasePage

            class LoggedInPage(BasePage):
                def get_username_displayed(self) -> str:
                    return "user"
        """).strip())

        page_obj = gf("pages/inventory_page.py", textwrap.dedent("""
            from pages.logged_in_page import LoggedInPage

            class InventoryPage(LoggedInPage):
                pass
        """).strip())

        step_def = gf("tests/step_defs/test_inv.py", textwrap.dedent("""
            import pytest
            from pytest_bdd import then
            from pages.inventory_page import InventoryPage

            @pytest.fixture
            def inventory_page(page):
                return InventoryPage(page)

            @then("ok")
            def verify(inventory_page):
                # navigate from BasePage, get_username_displayed from LoggedInPage
                inventory_page.navigate("x")
                assert inventory_page.get_username_displayed() == "user"
        """).strip())

        errors = validate_method_resolution([page_obj, step_def], fake_project)
        assert errors == []


# =============================================================================
# CLEAN BATCHES (no false positives)
# =============================================================================
class TestCleanCode:
    def test_consistent_naming_no_errors(self, fake_project: Path):
        """If page object and step def use matching names, validator stays silent."""
        page_obj = gf("pages/inventory_page.py", textwrap.dedent("""
            from pages.base_page import BasePage

            class InventoryPage(BasePage):
                def open_burger_menu(self) -> None: ...
                def click_logout(self) -> None: ...
                def is_logout_link_visible(self) -> bool: return True
        """).strip())

        step_def = gf("tests/step_defs/test_logout.py", textwrap.dedent("""
            import pytest
            from pytest_bdd import when, then
            from pages.inventory_page import InventoryPage

            @pytest.fixture
            def inventory_page(page):
                return InventoryPage(page)

            @when("I open menu")
            def open_menu(inventory_page):
                inventory_page.open_burger_menu()

            @when("I click logout")
            def do_logout(inventory_page):
                inventory_page.click_logout()

            @then("logout visible")
            def verify(inventory_page):
                assert inventory_page.is_logout_link_visible()
        """).strip())

        errors = validate_method_resolution([page_obj, step_def], fake_project)
        assert errors == []

    def test_only_page_objects_no_step_defs_no_errors(self, fake_project: Path):
        """If there are no step def files, validator has nothing to check."""
        page_obj = gf("pages/inventory_page.py", textwrap.dedent("""
            from pages.base_page import BasePage

            class InventoryPage(BasePage):
                def foo(self) -> None: ...
        """).strip())

        errors = validate_method_resolution([page_obj], fake_project)
        assert errors == []

    def test_existing_login_test_passes(self, fake_project: Path):
        """The existing test_login.py pattern (real file from the repo) passes."""
        step_def = gf("tests/step_defs/test_login.py", textwrap.dedent("""
            import pytest
            from pytest_bdd import scenarios, given, when, then, parsers
            from pages.login_page import LoginPage
            from pages.inventory_page import InventoryPage

            @pytest.fixture
            def login_page(page):
                return LoginPage(page)

            @pytest.fixture
            def inventory_page(page):
                return InventoryPage(page)

            @given("I am on the login page")
            def open_page(login_page, base_url):
                login_page.open(base_url)

            @when(parsers.parse('I login with "{u}" and "{p}"'))
            def login(login_page, u, p):
                login_page.login_as(u, p)

            @then(parsers.parse('error "{msg}"'))
            def verify_err(login_page, msg):
                assert login_page.get_error_message() == msg
        """).strip())

        # Add an InventoryPage to the on-disk project
        (fake_project / "pages" / "inventory_page.py").write_text(textwrap.dedent("""
            from pages.base_page import BasePage
            class InventoryPage(BasePage):
                def is_loaded(self) -> bool: return True
        """).strip())

        errors = validate_method_resolution([step_def], fake_project)
        assert errors == []


# =============================================================================
# FALSE-POSITIVE GUARDS
# =============================================================================
class TestFalsePositiveGuards:
    def test_playwright_page_calls_skipped(self, fake_project: Path):
        """`<page_obj>.page.click(...)` is a direct Playwright call, not validated."""
        page_obj = gf("pages/inventory_page.py", textwrap.dedent("""
            from pages.base_page import BasePage
            class InventoryPage(BasePage):
                pass
        """).strip())

        step_def = gf("tests/step_defs/test_inv.py", textwrap.dedent("""
            import pytest
            from pytest_bdd import when
            from pages.inventory_page import InventoryPage

            @pytest.fixture
            def inventory_page(page):
                return InventoryPage(page)

            @when("step")
            def do(inventory_page):
                # Direct Playwright API call — should not flag
                inventory_page.page.click("[data-test='foo']")
                inventory_page.page.fill("[data-test='bar']", "value")
                _ = inventory_page.page.url
        """).strip())

        errors = validate_method_resolution([page_obj, step_def], fake_project)
        assert errors == []

    def test_unknown_variable_not_flagged(self, fake_project: Path):
        """Calls on variables that aren't fixtures should be ignored."""
        step_def = gf("tests/step_defs/test_misc.py", textwrap.dedent("""
            import pytest
            from pytest_bdd import when
            import os

            @when("step")
            def do():
                # `os` is not a fixture — calls on it should not be validated
                _ = os.getenv("FOO")
                # local variable
                data = []
                data.append("x")
                data.fancy_method_that_doesnt_exist()  # not flagged either
        """).strip())

        errors = validate_method_resolution([step_def], fake_project)
        assert errors == []

    def test_call_when_class_unknown_silently_skipped(self, fake_project: Path):
        """If we can't resolve the class for a fixture, stay silent (no false positive)."""
        step_def = gf("tests/step_defs/test_unknown.py", textwrap.dedent("""
            import pytest
            from pytest_bdd import when

            # Note: NO import of MysteryPage — class is undefined
            @pytest.fixture
            def mystery_page(page):
                return MysteryPage(page)

            @when("step")
            def do(mystery_page):
                mystery_page.foo()
        """).strip())

        # Should NOT crash, should NOT flag — class unknown means no validation
        errors = validate_method_resolution([step_def], fake_project)
        assert errors == []

    def test_naming_convention_fallback_works(self, fake_project: Path):
        """If a step function uses `inventory_page` as a parameter without a
        local fixture, validator should still resolve it to InventoryPage."""
        page_obj = gf("pages/inventory_page.py", textwrap.dedent("""
            from pages.base_page import BasePage
            class InventoryPage(BasePage):
                def get_title(self) -> str:
                    return "Products"
        """).strip())

        # No @pytest.fixture for inventory_page in this file — it's expected to
        # come from a conftest.py. Naming-convention fallback should still work.
        step_def = gf("tests/step_defs/test_inv.py", textwrap.dedent("""
            from pytest_bdd import then
            from pages.inventory_page import InventoryPage

            @then("title shown")
            def verify(inventory_page):
                assert inventory_page.this_method_does_not_exist()
        """).strip())

        errors = validate_method_resolution([page_obj, step_def], fake_project)
        assert len(errors) == 1
        assert "this_method_does_not_exist" in errors[0]
        assert "InventoryPage" in errors[0]

    def test_non_step_def_files_not_validated(self, fake_project: Path):
        """A page object file calling its own missing method should NOT be
        flagged by THIS validator (only step_defs are scoped)."""
        page_obj = gf("pages/inventory_page.py", textwrap.dedent("""
            from pages.base_page import BasePage
            class InventoryPage(BasePage):
                def foo(self):
                    self.bar()  # bar doesn't exist, but this isn't a step def
        """).strip())

        errors = validate_method_resolution([page_obj], fake_project)
        # Validator only cares about tests/step_defs/ files
        assert errors == []


# =============================================================================
# ERROR FORMAT — must be parseable by the existing repair loop
# =============================================================================
class TestErrorFormat:
    def test_error_uses_standard_format(self, fake_project: Path):
        """Errors must match the `<type> error in '<path>':` pattern that
        _group_validator_errors_by_file regex parses."""
        import re

        page_obj = gf("pages/inventory_page.py", textwrap.dedent("""
            from pages.base_page import BasePage
            class InventoryPage(BasePage):
                def real_method(self): pass
        """).strip())

        step_def = gf("tests/step_defs/test_x.py", textwrap.dedent("""
            import pytest
            from pytest_bdd import when
            from pages.inventory_page import InventoryPage

            @pytest.fixture
            def inventory_page(page):
                return InventoryPage(page)

            @when("step")
            def do(inventory_page):
                inventory_page.fake_method()
        """).strip())

        errors = validate_method_resolution([page_obj, step_def], fake_project)
        assert len(errors) == 1
        # The repair loop's regex: r"error in '([^']+)':"
        match = re.search(r"error in '([^']+)':", errors[0])
        assert match is not None
        assert match.group(1) == "tests/step_defs/test_x.py"

    def test_error_includes_line_number(self, fake_project: Path):
        page_obj = gf("pages/inventory_page.py", textwrap.dedent("""
            from pages.base_page import BasePage
            class InventoryPage(BasePage):
                def real_method(self): pass
        """).strip())

        step_def = gf("tests/step_defs/test_x.py", textwrap.dedent("""
            import pytest
            from pytest_bdd import when
            from pages.inventory_page import InventoryPage

            @pytest.fixture
            def inventory_page(page):
                return InventoryPage(page)

            @when("step")
            def do(inventory_page):
                inventory_page.fake_method()
        """).strip())

        errors = validate_method_resolution([page_obj, step_def], fake_project)
        assert "line" in errors[0]


# =============================================================================
# UNIT TESTS for individual helpers
# =============================================================================
class TestParseClassMethods:
    def test_simple_class(self):
        src = textwrap.dedent("""
            class Foo:
                def a(self): pass
                def b(self): pass
        """).strip()
        assert _parse_class_methods(src, "Foo") == {"a", "b"}

    def test_class_not_found(self):
        src = "class Foo:\n    def a(self): pass"
        assert _parse_class_methods(src, "Bar") == set()

    def test_async_methods_included(self):
        src = textwrap.dedent("""
            class Foo:
                def sync_method(self): pass
                async def async_method(self): pass
        """).strip()
        assert _parse_class_methods(src, "Foo") == {"sync_method", "async_method"}

    def test_syntax_error_returns_empty(self):
        src = "class Foo:\n    def broken(self"
        assert _parse_class_methods(src, "Foo") == set()


class TestParseFixtures:
    def test_simple_fixture(self):
        src = textwrap.dedent("""
            import pytest
            @pytest.fixture
            def login_page(page):
                return LoginPage(page)
        """).strip()
        assert _parse_fixtures(src) == {"login_page": "LoginPage"}

    def test_multiple_fixtures(self):
        src = textwrap.dedent("""
            import pytest
            @pytest.fixture
            def login_page(page):
                return LoginPage(page)
            @pytest.fixture
            def inventory_page(page):
                return InventoryPage(page)
        """).strip()
        assert _parse_fixtures(src) == {
            "login_page": "LoginPage",
            "inventory_page": "InventoryPage",
        }

    def test_fixture_with_parameter_decorator(self):
        src = textwrap.dedent("""
            import pytest
            @pytest.fixture(scope="session")
            def login_page(page):
                return LoginPage(page)
        """).strip()
        assert _parse_fixtures(src) == {"login_page": "LoginPage"}

    def test_non_fixture_function_skipped(self):
        src = textwrap.dedent("""
            def helper():
                return LoginPage(None)
        """).strip()
        assert _parse_fixtures(src) == {}


class TestSimilarMethodSuggestions:
    def test_finds_similar_by_substring(self):
        suggestions = _find_similar_methods(
            "click_logout_link", {"click_logout", "open_menu", "is_loaded"}
        )
        assert "click_logout" in suggestions

    def test_finds_similar_by_token_overlap(self):
        suggestions = _find_similar_methods(
            "is_logout_link_in_menu_visible",
            {"is_logout_link_visible", "is_loaded", "open_menu"},
        )
        assert "is_logout_link_visible" in suggestions

    def test_no_similar_returns_empty(self):
        suggestions = _find_similar_methods(
            "totally_unrelated_xyz", {"open", "close", "fetch"}
        )
        assert suggestions == []

    def test_excludes_private_methods(self):
        suggestions = _find_similar_methods(
            "click_button", {"_click_internal", "click", "submit"}
        )
        assert "_click_internal" not in suggestions