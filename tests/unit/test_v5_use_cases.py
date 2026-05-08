"""Integration tests for Agent 2's three real-world use cases.

These tests do NOT call the LLM. They verify the validator + sibling-context
+ file-ordering pipeline ALL produce correct results for the realistic
input/output pairs that come out of Stage 2.

Use cases covered:

    UC1: NEW TEST GENERATION
         User creates a brand new story (e.g., logout) with brand new
         feature + step def + page object. All files generated fresh.

    UC2: EXTENDING EXISTING TEST (extending page object only)
         A new feature is added that uses an existing page object.
         The page object is extended with new methods; the feature
         file and step def are new.

    UC3: STEP-LEVEL MODIFICATIONS
         A repair-loop scenario: the LLM produced a step def with
         a method-name mismatch on the first try, and the validator
         catches it. The repair-loop regenerates the step def with
         feedback. The result must resolve cleanly.

Each test simulates Agent 2's real output structure and asserts the
end-to-end validation result. The goal: prove the framework will
behave correctly under realistic inputs after v5.
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from agents.agent2_coder import (
    _build_sibling_page_object_context,
    _collect_repairable_errors,
    _sort_files_for_generation,
)
from agents.schemas import FilePlan, GeneratedFile


# Helpers
def gf(path: str, content: str, is_new: bool = True) -> GeneratedFile:
    return GeneratedFile(
        file_path=path,
        content=content,
        is_new_file=is_new,
        purpose="test",
    )


def fp(path: str, ftype: str, is_new: bool = True) -> FilePlan:
    return FilePlan(
        file_path=path,
        file_type=ftype,
        is_new_file=is_new,
        purpose="test plan",
        related_test_cases=[],
    )


@pytest.fixture
def project_with_baseline(tmp_path: Path, monkeypatch) -> Path:
    """Build a fake project root with the same baseline as the real repo.

    Includes pages/base_page.py, pages/login_page.py, pages/inventory_page.py
    and tests/step_defs/test_login.py — matching the actual project state.
    Also includes a minimal requirements.txt so the import validator
    recognizes pytest, pytest_bdd, etc. as legitimate third-party deps.
    """
    # Build dirs
    pages = tmp_path / "pages"
    pages.mkdir()
    (pages / "__init__.py").write_text("")
    step_defs = tmp_path / "tests" / "step_defs"
    step_defs.mkdir(parents=True)
    (step_defs / "__init__.py").write_text("")
    features = tmp_path / "features"
    features.mkdir()
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "__init__.py").write_text("")
    (config_dir / "paths.py").write_text("def feature_path(name): return name")

    # Minimal requirements.txt so import validator recognizes 3rd-party deps
    (tmp_path / "requirements.txt").write_text(
        "pytest==8.3.3\n"
        "pytest-bdd==7.3.0\n"
        "playwright==1.48.0\n"
    )

    # Baseline pages
    (pages / "base_page.py").write_text(textwrap.dedent("""
        from playwright.sync_api import Page

        class BasePage:
            def __init__(self, page: Page):
                self.page = page

            def navigate(self, url: str) -> None:
                self.page.goto(url)
                self.page.wait_for_load_state("domcontentloaded")

            def is_visible(self, locator: str) -> bool:
                return self.page.locator(locator).is_visible()

            def get_title(self) -> str:
                return self.page.title()
    """).strip())

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
                if self.is_visible(self.ERROR_MESSAGE):
                    return self.page.locator(self.ERROR_MESSAGE).inner_text()
                return ""
    """).strip())

    (pages / "inventory_page.py").write_text(textwrap.dedent("""
        from pages.base_page import BasePage

        class InventoryPage(BasePage):
            PAGE_TITLE = "[data-test='title']"
            INVENTORY_CONTAINER = "[data-test='inventory-container']"
            URL_PATH = "/inventory.html"

            def is_loaded(self) -> bool:
                return self.URL_PATH in self.page.url and self.is_visible(self.INVENTORY_CONTAINER)

            def get_page_title_text(self) -> str:
                return self.page.locator(self.PAGE_TITLE).inner_text()
    """).strip())

    # Baseline feature + step def
    (features / "login.feature").write_text(textwrap.dedent("""
        Feature: Login
          Scenario: Login with valid creds
            Given I am on the login page
            When I log in with username "standard_user" and password "secret_sauce"
            Then I should be redirected to the inventory page
    """).strip())

    # Patch PROJECT_ROOT in the modules under test
    import agents.agent2_coder as mod_a2
    import agents.method_resolution_validator as mod_mrv
    import agents.import_validator as mod_iv
    monkeypatch.setattr(mod_a2, "PROJECT_ROOT", tmp_path)

    return tmp_path


# =============================================================================
# UC1: NEW TEST GENERATION
# =============================================================================
class TestUC1_NewTestGeneration:
    """Brand new story (e.g., a checkout flow) producing all-new files.

    Files generated:
        - features/checkout.feature   (new)
        - tests/step_defs/test_checkout.py  (new)
        - pages/checkout_page.py  (new)

    Expected v5 behavior:
        1. _sort_files_for_generation puts pages before step defs
        2. When step def is generated, sibling context includes
           checkout_page.py method signatures
        3. Validators all pass on a clean, consistent batch
    """

    def test_clean_new_test_generation_passes_validators(self, project_with_baseline: Path):
        # Simulate Stage 2 output for a fresh "checkout" feature
        feature_content = textwrap.dedent("""
            Feature: Checkout
              @smoke
              Scenario: Successful checkout
                Given I am on the inventory page
                When I add an item to cart
                Then I should see the cart count increase
        """).strip()

        page_object_content = textwrap.dedent("""
            from pages.base_page import BasePage

            class CheckoutPage(BasePage):
                ADD_TO_CART_BUTTON = "[data-test='add-to-cart-sauce-labs-backpack']"
                CART_COUNT = "[data-test='shopping-cart-badge']"

                def add_first_item_to_cart(self) -> None:
                    self.page.click(self.ADD_TO_CART_BUTTON)

                def get_cart_count(self) -> int:
                    if self.is_visible(self.CART_COUNT):
                        return int(self.page.locator(self.CART_COUNT).inner_text())
                    return 0
        """).strip()

        step_def_content = textwrap.dedent("""
            import pytest
            from pytest_bdd import scenarios, given, when, then
            from pages.inventory_page import InventoryPage
            from pages.checkout_page import CheckoutPage
            from config.paths import feature_path

            scenarios(str(feature_path("checkout")))

            @pytest.fixture
            def inventory_page(page):
                return InventoryPage(page)

            @pytest.fixture
            def checkout_page(page):
                return CheckoutPage(page)

            @given("I am on the inventory page")
            def open_inventory(inventory_page):
                assert inventory_page.is_loaded()

            @when("I add an item to cart")
            def add_item(checkout_page):
                checkout_page.add_first_item_to_cart()

            @then("I should see the cart count increase")
            def verify_count(checkout_page):
                assert checkout_page.get_cart_count() > 0
        """).strip()

        files = [
            gf("features/checkout.feature", feature_content),
            gf("pages/checkout_page.py", page_object_content),
            gf("tests/step_defs/test_checkout.py", step_def_content),
        ]

        errors = _collect_repairable_errors(files)
        assert errors == [], f"UC1 should have NO errors, got: {errors}"

    def test_uc1_file_ordering_puts_page_object_before_step_def(self):
        """File ordering must guarantee page object generates first."""
        plans = [
            fp("tests/step_defs/test_checkout.py", "step_definitions"),
            fp("pages/checkout_page.py", "page_object"),
            fp("features/checkout.feature", "feature"),
        ]
        ordered = _sort_files_for_generation(plans)
        types_in_order = [p.file_type for p in ordered]
        assert types_in_order == ["feature", "page_object", "step_definitions"]

    def test_uc1_sibling_context_provides_method_signatures(self):
        """When step def is generated AFTER page object, sibling context
        must list the page object's method signatures."""
        page_obj = gf("pages/checkout_page.py", textwrap.dedent("""
            from pages.base_page import BasePage
            class CheckoutPage(BasePage):
                def add_first_item_to_cart(self) -> None: pass
                def get_cart_count(self) -> int: return 0
                def _private_helper(self): pass  # excluded
        """).strip())

        block = _build_sibling_page_object_context([page_obj])
        assert "CheckoutPage" in block
        assert "add_first_item_to_cart" in block
        assert "get_cart_count" in block
        assert "_private_helper" not in block, "private methods should be excluded"
        assert "USE THESE EXACT NAMES" in block

    def test_uc1_caught_if_step_def_invents_method_name(
        self, project_with_baseline: Path
    ):
        """v5 catches it if the LLM still hallucinates a method name."""
        page_object_content = textwrap.dedent("""
            from pages.base_page import BasePage

            class CheckoutPage(BasePage):
                def add_first_item_to_cart(self) -> None: pass
        """).strip()

        # Step def calls add_item_to_cart_now (BUG — page object has add_first_item_to_cart)
        step_def_content = textwrap.dedent("""
            import pytest
            from pytest_bdd import when
            from pages.checkout_page import CheckoutPage

            @pytest.fixture
            def checkout_page(page):
                return CheckoutPage(page)

            @when("I add item")
            def do(checkout_page):
                checkout_page.add_item_to_cart_now()
        """).strip()

        files = [
            gf("pages/checkout_page.py", page_object_content),
            gf("tests/step_defs/test_checkout.py", step_def_content),
        ]
        errors = _collect_repairable_errors(files)
        assert any("add_item_to_cart_now" in e for e in errors)
        assert any("add_first_item_to_cart" in e for e in errors), \
            "Error should suggest the correct method name"


# =============================================================================
# UC2: EXTENDING EXISTING TEST (page object grows)
# =============================================================================
class TestUC2_ExtendExistingPage:
    """A new feature uses methods from an EXISTING page object.

    Realistic example: SCRUM-23 logout extends inventory_page.py with
    new methods (open_burger_menu, click_logout, is_logout_link_visible).

    Expected v5 behavior:
        1. inventory_page.py is generated WITH the new methods (extending
           the existing class definition — old methods preserved)
        2. Step def references both old (inherited) and new methods
        3. Validator confirms all method calls resolve
    """

    def test_uc2_extending_inventory_page_for_logout(
        self, project_with_baseline: Path
    ):
        # The extended page object contains the original methods (is_loaded,
        # get_page_title_text) PLUS the new logout methods.
        extended_inventory = textwrap.dedent("""
            from pages.base_page import BasePage

            class InventoryPage(BasePage):
                # Original
                PAGE_TITLE = "[data-test='title']"
                INVENTORY_CONTAINER = "[data-test='inventory-container']"
                URL_PATH = "/inventory.html"
                # New for logout
                BURGER_MENU_BUTTON = "#react-burger-menu-btn"
                LOGOUT_LINK = "#logout_sidebar_link"

                # Original methods (preserved)
                def is_loaded(self) -> bool:
                    return self.URL_PATH in self.page.url

                def get_page_title_text(self) -> str:
                    return self.page.locator(self.PAGE_TITLE).inner_text()

                # New methods
                def open_burger_menu(self) -> None:
                    self.page.click(self.BURGER_MENU_BUTTON)

                def click_logout(self) -> None:
                    self.page.click(self.LOGOUT_LINK)

                def is_logout_link_visible(self) -> bool:
                    return self.is_visible(self.LOGOUT_LINK)
        """).strip()

        feature_content = textwrap.dedent("""
            Feature: Logout
              Scenario: Logout returns to login page
                Given I am on the inventory page
                When I open the burger menu
                And I click logout
                Then I should be on the login page
        """).strip()

        step_def_content = textwrap.dedent("""
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

            @given("I am on the inventory page")
            def on_inventory(inventory_page):
                assert inventory_page.is_loaded()  # inherited from original

            @when("I open the burger menu")
            def open_menu(inventory_page):
                inventory_page.open_burger_menu()  # new method

            @when("I click logout")
            def do_logout(inventory_page):
                inventory_page.click_logout()  # new method

            @then("I should be on the login page")
            def verify_login(login_page):
                # is_visible inherited from BasePage
                assert login_page.is_visible(login_page.LOGIN_BUTTON)
        """).strip()

        files = [
            gf("features/logout.feature", feature_content),
            gf("pages/inventory_page.py", extended_inventory, is_new=False),
            gf("tests/step_defs/test_logout.py", step_def_content),
        ]

        errors = _collect_repairable_errors(files)
        assert errors == [], f"UC2 should have NO errors, got: {errors}"

    def test_uc2_breaks_if_old_method_was_dropped(
        self, project_with_baseline: Path
    ):
        """If the LLM accidentally drops an existing method when extending,
        any step def call to that method is caught."""
        # extended_inventory accidentally LOST is_loaded()
        broken_extended = textwrap.dedent("""
            from pages.base_page import BasePage
            class InventoryPage(BasePage):
                # ORIGINAL is_loaded() was accidentally removed!
                def open_burger_menu(self): pass
                def click_logout(self): pass
        """).strip()

        step_def_content = textwrap.dedent("""
            import pytest
            from pytest_bdd import given
            from pages.inventory_page import InventoryPage

            @pytest.fixture
            def inventory_page(page):
                return InventoryPage(page)

            @given("on inv page")
            def on_inv(inventory_page):
                assert inventory_page.is_loaded()  # BUG: not defined anymore
        """).strip()

        files = [
            gf("pages/inventory_page.py", broken_extended, is_new=False),
            gf("tests/step_defs/test_logout.py", step_def_content),
        ]
        errors = _collect_repairable_errors(files)
        assert any("is_loaded" in e for e in errors), \
            "v5 should catch dropped methods from the extended file"

    def test_uc2_sibling_context_includes_extended_page(
        self, project_with_baseline: Path
    ):
        """Sibling context for the step-def prompt must include the
        extended page object's full method list (old + new)."""
        extended_inventory = textwrap.dedent("""
            from pages.base_page import BasePage
            class InventoryPage(BasePage):
                def is_loaded(self) -> bool: return True
                def get_page_title_text(self) -> str: return ""
                def open_burger_menu(self) -> None: pass
                def click_logout(self) -> None: pass
                def is_logout_link_visible(self) -> bool: return True
        """).strip()

        block = _build_sibling_page_object_context([
            gf("pages/inventory_page.py", extended_inventory, is_new=False)
        ])
        # Both old and new methods must appear
        assert "is_loaded" in block
        assert "get_page_title_text" in block
        assert "open_burger_menu" in block
        assert "click_logout" in block
        assert "is_logout_link_visible" in block


# =============================================================================
# UC3: STEP-LEVEL MODIFICATIONS (the actual SCRUM-23 failure shape)
# =============================================================================
class TestUC3_StepLevelModifications:
    """The repair-loop scenario.

    First Stage 2 attempt produces a step def with method-name mismatches.
    The validator catches them. The repair loop regenerates with feedback.
    The corrected output passes.

    Critical: this is the EXACT flow that would have prevented SCRUM-23.
    """

    def test_uc3_first_attempt_caught_with_repair_friendly_errors(
        self, project_with_baseline: Path
    ):
        """The bugs from the SCRUM-23 logout run, in their actual form.
        v5 must produce errors that the repair loop can target by file."""
        page_object_content = textwrap.dedent("""
            from pages.base_page import BasePage
            class InventoryPage(BasePage):
                def open_burger_menu(self): pass
                def click_logout(self): pass
                def is_logout_link_visible(self): return True
        """).strip()

        # First attempt — three method-name mismatches (the actual SCRUM-23 bugs)
        broken_step_def = textwrap.dedent("""
            import pytest
            from pytest_bdd import when, then
            from pages.inventory_page import InventoryPage
            from pages.login_page import LoginPage

            @pytest.fixture
            def inventory_page(page):
                return InventoryPage(page)

            @pytest.fixture
            def login_page(page):
                return LoginPage(page)

            @when("I click logout option")
            def click_opt(inventory_page):
                inventory_page.click_logout_link()  # BUG 1

            @then("logout option visible")
            def verify_logout(inventory_page):
                assert inventory_page.is_logout_link_in_menu_visible()  # BUG 2

            @then("login form fields visible")
            def verify_form(login_page):
                assert login_page.are_login_form_fields_visible()  # BUG 3
        """).strip()

        files = [
            gf("pages/inventory_page.py", page_object_content),
            gf("tests/step_defs/test_logout.py", broken_step_def),
        ]
        errors = _collect_repairable_errors(files)

        # All 3 bugs caught
        assert len(errors) == 3
        # All 3 errors target the same file (so the repair loop groups them)
        assert all("tests/step_defs/test_logout.py" in e for e in errors)
        # The error format matches what the repair-loop's regex expects
        import re
        for e in errors:
            assert re.search(r"error in '([^']+)':", e) is not None, \
                f"Error format must match repair-loop regex: {e}"

    def test_uc3_corrected_step_def_passes_after_repair(
        self, project_with_baseline: Path
    ):
        """After repair (LLM uses sibling context + validator feedback),
        the corrected step def passes all validators."""
        page_object_content = textwrap.dedent("""
            from pages.base_page import BasePage
            class InventoryPage(BasePage):
                def open_burger_menu(self): pass
                def click_logout(self): pass
                def is_logout_link_visible(self): return True
        """).strip()

        # The CORRECTED version
        fixed_step_def = textwrap.dedent("""
            import pytest
            from pytest_bdd import when, then
            from pages.inventory_page import InventoryPage
            from pages.login_page import LoginPage

            @pytest.fixture
            def inventory_page(page):
                return InventoryPage(page)

            @pytest.fixture
            def login_page(page):
                return LoginPage(page)

            @when("I click logout option")
            def click_opt(inventory_page):
                inventory_page.click_logout()  # FIXED

            @then("logout option visible")
            def verify_logout(inventory_page):
                assert inventory_page.is_logout_link_visible()  # FIXED

            @then("login form fields visible")
            def verify_form(login_page):
                # Use the actual method that exists on LoginPage
                assert login_page.is_visible(login_page.USERNAME_INPUT)
                assert login_page.is_visible(login_page.PASSWORD_INPUT)
        """).strip()

        files = [
            gf("pages/inventory_page.py", page_object_content),
            gf("tests/step_defs/test_logout.py", fixed_step_def),
        ]
        errors = _collect_repairable_errors(files)
        assert errors == [], f"After repair, expected NO errors, got: {errors}"

    def test_uc3_partial_fix_still_catches_remaining_bugs(
        self, project_with_baseline: Path
    ):
        """If the repair fixes 2 of 3 bugs, the validator still catches
        the remaining one — the repair loop will retry it (within max=2)."""
        page_object_content = textwrap.dedent("""
            from pages.base_page import BasePage
            class InventoryPage(BasePage):
                def click_logout(self): pass
                def is_logout_link_visible(self): return True
        """).strip()

        partially_fixed = textwrap.dedent("""
            import pytest
            from pytest_bdd import when, then
            from pages.inventory_page import InventoryPage
            from pages.login_page import LoginPage

            @pytest.fixture
            def inventory_page(page):
                return InventoryPage(page)

            @pytest.fixture
            def login_page(page):
                return LoginPage(page)

            @when("I click logout option")
            def click_opt(inventory_page):
                inventory_page.click_logout()  # FIXED

            @then("logout option visible")
            def verify_logout(inventory_page):
                assert inventory_page.is_logout_link_visible()  # FIXED

            @then("login form fields visible")
            def verify_form(login_page):
                # Still wrong — should be is_visible() with locator constants
                assert login_page.are_login_form_fields_visible()  # STILL BUG
        """).strip()

        files = [
            gf("pages/inventory_page.py", page_object_content),
            gf("tests/step_defs/test_logout.py", partially_fixed),
        ]
        errors = _collect_repairable_errors(files)
        assert len(errors) == 1
        assert "are_login_form_fields_visible" in errors[0]


# =============================================================================
# CROSS-USE-CASE: previously-failing test_empty_quoted_value also works
# =============================================================================
class TestPreExistingEmptyQuotedRegression:
    """The pre-existing test that used to fail in environments without `parse`
    is now solid: parse is an explicit dep, and the validator's lazy import
    has a loud warning fallback."""

    def test_empty_quoted_with_parsers_parse_caught(self):
        """Reaffirm: parsers.parse + empty "" still flags an error pointing
        to parsers.re as the fix."""
        from agents.test_inventory import validate_step_definitions_complete

        feature = (
            "Feature: Login\n"
            "  Scenario: Empty username\n"
            '    When I log in with username "" and password "secret"\n'
        )
        step_def = (
            "from pytest_bdd import when, parsers\n"
            "@when(parsers.parse('I log in with username \"{u}\" and password \"{p}\"'))\n"
            "def s1(u, p): pass\n"
        )
        files = [
            gf("features/login.feature", feature),
            gf("tests/step_defs/test_login.py", step_def),
        ]
        errors = validate_step_definitions_complete(files)
        assert len(errors) == 1
        assert "parsers.re" in errors[0]

    def test_empty_quoted_with_parsers_re_passes(self):
        """And parsers.re with [^"]* correctly passes."""
        from agents.test_inventory import validate_step_definitions_complete

        feature = (
            "Feature: Login\n"
            "  Scenario: Empty username\n"
            '    When I log in with username "" and password "secret"\n'
        )
        step_def = (
            "from pytest_bdd import when, parsers\n"
            "@when(parsers.re(r'I log in with username \"(?P<u>[^\"]*)\" and password \"(?P<p>[^\"]*)\"'))\n"
            "def s1(u, p): pass\n"
        )
        files = [
            gf("features/login.feature", feature),
            gf("tests/step_defs/test_login.py", step_def),
        ]
        errors = validate_step_definitions_complete(files)
        assert errors == []