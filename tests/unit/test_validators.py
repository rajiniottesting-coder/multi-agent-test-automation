"""Regression tests for Agent 2's validators.

This file consolidates all validator tests into one focused suite. Each
test corresponds to a real production failure mode that bit us at least
once, with a regression test that locks the fix in place.

Validators covered (in order of historical introduction):

    1. Filename consistency        — feature/step-def kebab vs snake mismatch
    2. Step coverage               — missing @given/@when/@then decorators
    3. Empty quoted values         — parsers.parse "" runtime trap
    4. Path policy (Hotfix v1)     — reserved file overwrite, extendable allowed
    5. Import resolution (v3)      — hallucinated module imports
    6. Method resolution (v5)      — cross-file method-name mismatches

Design philosophy (after the v5 cleanup):

    - One test per real production failure shape. Not per code branch.
    - Use realistic inputs (feature files, page objects, step defs)
      that mirror what Agent 2 actually generates.
    - Skip granular helper-function tests — the integration-level tests
      exercise them indirectly. If a helper changes and integration
      still passes, no one cares.
    - Keep names short and descriptive. The name IS the documentation.
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from agents.test_inventory import (
    validate_filename_consistency,
    validate_step_definitions_complete,
)
from agents.import_validator import validate_imports_resolvable
from agents.method_resolution_validator import validate_method_resolution
from agents.app_context import AppContext
from agents.agent2_coder import validate_paths_against_policy
from agents.schemas import GeneratedFile


# Helper: build a GeneratedFile from a path and content
def gf(path: str, content: str, is_new: bool = True) -> GeneratedFile:
    return GeneratedFile(file_path=path, content=content, is_new_file=is_new, purpose="test")


# Helper: build a fake project with the same baseline as the real repo
@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    """Minimal project layout matching the real SauceDemo baseline."""
    (tmp_path / "pages").mkdir()
    (tmp_path / "pages" / "__init__.py").write_text("")
    (tmp_path / "tests" / "step_defs").mkdir(parents=True)
    (tmp_path / "tests" / "step_defs" / "__init__.py").write_text("")
    (tmp_path / "features").mkdir()
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "__init__.py").write_text("")

    # requirements so import-validator recognizes 3rd-party deps
    (tmp_path / "requirements.txt").write_text(
        "pytest==8.3.3\npytest-bdd==7.3.0\nplaywright==1.48.0\nparse>=1.20.0\n"
    )

    # BasePage (mirrors real repo)
    (tmp_path / "pages" / "base_page.py").write_text(textwrap.dedent("""
        from playwright.sync_api import Page

        class BasePage:
            def __init__(self, page: Page):
                self.page = page
            def navigate(self, url: str) -> None:
                self.page.goto(url)
            def is_visible(self, locator: str) -> bool:
                return self.page.locator(locator).is_visible()
    """).strip())

    # LoginPage (RESERVED — must never be modified)
    (tmp_path / "pages" / "login_page.py").write_text(textwrap.dedent("""
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

    # InventoryPage (EXTENDABLE)
    (tmp_path / "pages" / "inventory_page.py").write_text(textwrap.dedent("""
        from pages.base_page import BasePage

        class InventoryPage(BasePage):
            URL_PATH = "/inventory.html"
            INVENTORY_CONTAINER = "[data-test='inventory-container']"

            def is_loaded(self) -> bool:
                return self.URL_PATH in self.page.url
    """).strip())
    return tmp_path


# =============================================================================
# 1. Filename consistency (PR #7 regression)
# =============================================================================
class TestFilenameConsistency:
    """The validator must catch when a step def's `feature_path("...")`
    argument doesn't match the paired feature filename.
    """

    def test_kebab_vs_snake_mismatch_autocorrected(self):
        feature = gf("features/login_validation.feature", "Feature: x\n")
        step_def = gf(
            "tests/step_defs/test_login_validation.py",
            'from config.paths import feature_path\nscenarios(str(feature_path("login-validation")))\n',
        )
        errors = validate_filename_consistency([feature, step_def])
        # Kebab/snake mismatch is auto-corrected internally, no error surfaces
        assert errors == []

    def test_unrelated_name_caught(self):
        feature = gf("features/login.feature", "Feature: x\n")
        step_def = gf(
            "tests/step_defs/test_login.py",
            'from config.paths import feature_path\nscenarios(str(feature_path("checkout")))\n',
        )
        errors = validate_filename_consistency([feature, step_def])
        assert len(errors) == 1
        assert "checkout" in errors[0]


# =============================================================================
# 2. Step coverage (PR #9 — missing decorators)
# =============================================================================
class TestStepCoverage:
    """Every Gherkin step must have a matching @given/@when/@then decorator."""

    def test_complete_coverage_no_errors(self):
        feature = gf("features/x.feature", textwrap.dedent("""
            Feature: x
              Scenario: y
                Given I am on the login page
                When I click the button
                Then I see success
        """).strip())
        step_def = gf("tests/step_defs/test_x.py", textwrap.dedent("""
            from pytest_bdd import given, when, then
            @given("I am on the login page")
            def s1(): pass
            @when("I click the button")
            def s2(): pass
            @then("I see success")
            def s3(): pass
        """).strip())
        assert validate_step_definitions_complete([feature, step_def]) == []

    def test_missing_decorator_caught(self):
        feature = gf("features/x.feature", textwrap.dedent("""
            Feature: x
              Scenario: y
                Given I am on the login page
                When I do a missing thing
                Then I see success
        """).strip())
        step_def = gf("tests/step_defs/test_x.py", textwrap.dedent("""
            from pytest_bdd import given, then
            @given("I am on the login page")
            def s1(): pass
            @then("I see success")
            def s3(): pass
        """).strip())
        errors = validate_step_definitions_complete([feature, step_def])
        assert len(errors) == 1
        assert "I do a missing thing" in errors[0]

    def test_and_inherits_previous_keyword(self):
        """`And` inherits Given/When/Then from the previous line. The
        validator must look up the right kind."""
        feature = gf("features/x.feature", textwrap.dedent("""
            Feature: x
              Scenario: y
                Then I see the title
                And I see the count
        """).strip())
        step_def = gf("tests/step_defs/test_x.py", textwrap.dedent("""
            from pytest_bdd import then
            @then("I see the title")
            def s1(): pass
            @then("I see the count")
            def s2(): pass
        """).strip())
        assert validate_step_definitions_complete([feature, step_def]) == []


# =============================================================================
# 3. Empty quoted values (the parsers.parse "" runtime trap)
# =============================================================================
class TestEmptyQuotedValues:
    """parsers.parse('...{u}...') doesn't match empty quoted values at runtime
    (parse library limitation). The validator must catch this and suggest
    parsers.re as the fix.
    """

    def test_empty_value_with_parsers_parse_caught_with_fix_hint(self):
        feature = gf("features/x.feature", textwrap.dedent("""
            Feature: x
              Scenario: y
                When I log in with username "" and password "secret"
        """).strip())
        step_def = gf("tests/step_defs/test_x.py", textwrap.dedent("""
            from pytest_bdd import when, parsers
            @when(parsers.parse('I log in with username "{u}" and password "{p}"'))
            def s1(u, p): pass
        """).strip())
        errors = validate_step_definitions_complete([feature, step_def])
        assert len(errors) == 1
        assert "parsers.re" in errors[0], "Error must hint parsers.re as the fix"

    def test_parsers_re_with_empty_pattern_passes(self):
        feature = gf("features/x.feature", textwrap.dedent("""
            Feature: x
              Scenario: y
                When I log in with username "" and password "secret"
        """).strip())
        step_def = gf("tests/step_defs/test_x.py", textwrap.dedent("""
            from pytest_bdd import when, parsers
            @when(parsers.re(r'I log in with username "(?P<u>[^"]*)" and password "(?P<p>[^"]*)"'))
            def s1(u, p): pass
        """).strip())
        assert validate_step_definitions_complete([feature, step_def]) == []


# =============================================================================
# 4. Path policy (Hotfix v1)
# =============================================================================
class _FakeFP:
    """Minimal stand-in for FilePlan — validator only reads two attributes."""
    def __init__(self, file_path: str, is_new_file: bool):
        self.file_path = file_path
        self.is_new_file = is_new_file


class _FakePlan:
    def __init__(self, files):
        self.files_to_create = files


@pytest.fixture
def policy_ctx():
    """AppContext with both reserved and extendable paths configured."""
    return AppContext(
        name="TestApp",
        base_url="https://example.com",
        inventory_file="app_inventory/test.json",
        reference_feature="features/login.feature",
        reference_step_def="tests/step_defs/test_login.py",
        reference_page_object="pages/login_page.py",
        reserved_paths=(
            "features/login.feature",
            "tests/step_defs/test_login.py",
            "pages/login_page.py",
        ),
        extendable_paths=("pages/inventory_page.py",),
    )


class TestPathPolicy:
    """Reserved files (e.g., login_page.py) must never be overwritten.
    Extendable files (e.g., inventory_page.py) may be modified additively.
    """

    def test_brand_new_file_accepted(self, policy_ctx):
        plan = _FakePlan([_FakeFP("pages/cart_page.py", True)])
        validate_paths_against_policy(plan, policy_ctx)  # no exception

    def test_reserved_file_overwrite_rejected(self, policy_ctx):
        plan = _FakePlan([_FakeFP("pages/login_page.py", True)])
        with pytest.raises(ValueError, match="reserved"):
            validate_paths_against_policy(plan, policy_ctx)

    def test_extendable_modification_accepted(self, policy_ctx):
        plan = _FakePlan([_FakeFP("pages/inventory_page.py", False)])
        validate_paths_against_policy(plan, policy_ctx)

    def test_extendable_marked_as_new_rejected(self, policy_ctx):
        """is_new_file=True on an extendable path would wipe existing methods."""
        plan = _FakePlan([_FakeFP("pages/inventory_page.py", True)])
        with pytest.raises(ValueError, match="extendable"):
            validate_paths_against_policy(plan, policy_ctx)


# =============================================================================
# 5. Import resolution (Hotfix v3 — SCRUM-13 regression)
# =============================================================================
class TestImportResolution:
    """The LLM hallucinated `from pages.product_detail_page import
    ProductDetailPage` when no such file was planned. Validator catches
    this before tests crash at collection time.
    """

    def test_hallucinated_import_caught(self, project_root: Path):
        # Step def imports a page that doesn't exist anywhere
        step_def = gf("tests/step_defs/test_x.py", textwrap.dedent("""
            from pages.nonexistent_page import NonexistentPage
            def s1(): pass
        """).strip())
        errors = validate_imports_resolvable([step_def], project_root)
        assert any("nonexistent_page" in e for e in errors)

    def test_existing_import_passes(self, project_root: Path):
        step_def = gf("tests/step_defs/test_x.py", textwrap.dedent("""
            from pages.login_page import LoginPage
            from pages.inventory_page import InventoryPage
            import pytest
            def s1(): pass
        """).strip())
        assert validate_imports_resolvable([step_def], project_root) == []

    def test_planned_in_batch_passes(self, project_root: Path):
        """Importing a page object that's being created in this same batch
        should pass — it'll exist when the PR is merged."""
        new_page = gf("pages/cart_page.py", "from pages.base_page import BasePage\nclass CartPage(BasePage): pass")
        step_def = gf("tests/step_defs/test_cart.py", textwrap.dedent("""
            from pages.cart_page import CartPage
            def s1(): pass
        """).strip())
        assert validate_imports_resolvable([new_page, step_def], project_root) == []


# =============================================================================
# 6. Method resolution (Hotfix v5 — SCRUM-23 regression)
# =============================================================================
class TestMethodResolution:
    """The LLM defines `click_logout()` in inventory_page.py but calls
    `click_logout_link()` in test_logout.py. AttributeError at runtime.
    Validator catches the cross-file naming inconsistency.
    """

    def test_cross_file_name_mismatch_caught(self, project_root: Path):
        # Page object defines click_logout
        page_obj = gf("pages/inventory_page.py", textwrap.dedent("""
            from pages.base_page import BasePage
            class InventoryPage(BasePage):
                def click_logout(self) -> None: pass
                def is_logout_link_visible(self) -> bool: return True
        """).strip())
        # Step def calls click_logout_link  (BUG)
        step_def = gf("tests/step_defs/test_logout.py", textwrap.dedent("""
            import pytest
            from pytest_bdd import when
            from pages.inventory_page import InventoryPage

            @pytest.fixture
            def inventory_page(page):
                return InventoryPage(page)

            @when("I click logout")
            def do(inventory_page):
                inventory_page.click_logout_link()
        """).strip())

        errors = validate_method_resolution([page_obj, step_def], project_root)
        assert len(errors) == 1
        assert "click_logout_link" in errors[0]
        assert "click_logout" in errors[0]  # suggested fix

    def test_hallucinated_method_on_reserved_page_caught(self, project_root: Path):
        """LoginPage is reserved (read from disk). The LLM calls a method
        that doesn't exist on it. Must be caught."""
        step_def = gf("tests/step_defs/test_logout.py", textwrap.dedent("""
            import pytest
            from pytest_bdd import then
            from pages.login_page import LoginPage

            @pytest.fixture
            def login_page(page):
                return LoginPage(page)

            @then("login form visible")
            def s1(login_page):
                assert login_page.are_login_form_fields_visible()
        """).strip())
        errors = validate_method_resolution([step_def], project_root)
        assert len(errors) == 1
        assert "are_login_form_fields_visible" in errors[0]

    def test_inherited_basepage_methods_accepted(self, project_root: Path):
        """Methods inherited from BasePage (e.g., is_visible, navigate)
        are valid even when the subclass doesn't redefine them."""
        page_obj = gf("pages/inventory_page.py", textwrap.dedent("""
            from pages.base_page import BasePage
            class InventoryPage(BasePage):
                CONTAINER = "[data-test='c']"
        """).strip())
        step_def = gf("tests/step_defs/test_x.py", textwrap.dedent("""
            import pytest
            from pytest_bdd import then
            from pages.inventory_page import InventoryPage

            @pytest.fixture
            def inventory_page(page):
                return InventoryPage(page)

            @then("ok")
            def s1(inventory_page):
                inventory_page.navigate("https://x.com")
                assert inventory_page.is_visible(inventory_page.CONTAINER)
        """).strip())
        assert validate_method_resolution([page_obj, step_def], project_root) == []

    def test_consistent_naming_no_errors(self, project_root: Path):
        """When page object and step def use matching names, no errors."""
        page_obj = gf("pages/inventory_page.py", textwrap.dedent("""
            from pages.base_page import BasePage
            class InventoryPage(BasePage):
                def click_logout(self): pass
        """).strip())
        step_def = gf("tests/step_defs/test_logout.py", textwrap.dedent("""
            import pytest
            from pytest_bdd import when
            from pages.inventory_page import InventoryPage

            @pytest.fixture
            def inventory_page(page):
                return InventoryPage(page)

            @when("I click logout")
            def s1(inventory_page):
                inventory_page.click_logout()
        """).strip())
        assert validate_method_resolution([page_obj, step_def], project_root) == []

    def test_playwright_page_calls_skipped(self, project_root: Path):
        """Direct Playwright calls like `inventory_page.page.click(...)`
        are NOT validated — Playwright's API is external."""
        page_obj = gf("pages/inventory_page.py", textwrap.dedent("""
            from pages.base_page import BasePage
            class InventoryPage(BasePage): pass
        """).strip())
        step_def = gf("tests/step_defs/test_x.py", textwrap.dedent("""
            import pytest
            from pytest_bdd import when
            from pages.inventory_page import InventoryPage

            @pytest.fixture
            def inventory_page(page):
                return InventoryPage(page)

            @when("step")
            def s1(inventory_page):
                inventory_page.page.click("[data-test='foo']")
        """).strip())
        assert validate_method_resolution([page_obj, step_def], project_root) == []


# =============================================================================
# 7. Generalization — validators work for ANY feature, not just logout
# =============================================================================
class TestGeneralization:
    """The validator infrastructure must not be tied to the specific bugs
    that prompted each hotfix. It must work for any future feature on any
    web app. These tests use deliberately different domains (banking,
    e-commerce checkout, account profile) to prove the validators are
    truly app-agnostic.
    """

    def test_method_resolution_catches_bug_in_banking_app(self, tmp_path: Path):
        """Banking-app domain: page object defines `transfer_funds()`,
        step def calls `transfer_money()`. v5 must catch this just like
        it caught the logout bug — no domain-specific assumptions."""
        # Build a banking-style project from scratch (no SauceDemo baseline)
        (tmp_path / "pages").mkdir()
        (tmp_path / "pages" / "__init__.py").write_text("")
        (tmp_path / "pages" / "base_page.py").write_text(textwrap.dedent("""
            from playwright.sync_api import Page
            class BasePage:
                def __init__(self, page: Page):
                    self.page = page
                def is_visible(self, locator: str) -> bool:
                    return self.page.locator(locator).is_visible()
        """).strip())
        (tmp_path / "tests" / "step_defs").mkdir(parents=True)
        (tmp_path / "tests" / "step_defs" / "__init__.py").write_text("")
        (tmp_path / "requirements.txt").write_text("pytest\npytest-bdd\nplaywright\n")

        accounts_page = gf("pages/accounts_page.py", textwrap.dedent("""
            from pages.base_page import BasePage
            class AccountsPage(BasePage):
                def transfer_funds(self, amount: float, to_account: str) -> None:
                    pass
                def get_balance(self) -> float:
                    return 0.0
        """).strip())

        step_def = gf("tests/step_defs/test_transfers.py", textwrap.dedent("""
            import pytest
            from pytest_bdd import when, then
            from pages.accounts_page import AccountsPage

            @pytest.fixture
            def accounts_page(page):
                return AccountsPage(page)

            @when("I transfer 100 to savings")
            def do_transfer(accounts_page):
                accounts_page.transfer_money(100, "savings")

            @then("balance updates")
            def verify(accounts_page):
                assert accounts_page.check_balance() > 0
        """).strip())

        errors = validate_method_resolution([accounts_page, step_def], tmp_path)
        assert len(errors) == 2
        # Both errors target the same file, with helpful suggestions
        assert all("tests/step_defs/test_transfers.py" in e for e in errors)
        assert any("transfer_money" in e and "transfer_funds" in e for e in errors)
        assert any("check_balance" in e and "get_balance" in e for e in errors)

    def test_step_coverage_works_for_arbitrary_domain(self):
        """Step coverage validator has no domain knowledge. A profile
        feature with completely different verbs and nouns must work
        identically to a logout feature."""
        feature = gf("features/profile.feature", textwrap.dedent("""
            Feature: Profile management
              Scenario: Update display name
                Given I am viewing my profile
                When I edit my display name to "Alice"
                Then my profile shows "Alice"
        """).strip())
        # Step def is missing the @when decorator
        step_def = gf("tests/step_defs/test_profile.py", textwrap.dedent("""
            from pytest_bdd import given, then, parsers
            @given("I am viewing my profile")
            def s1(): pass
            @then(parsers.parse('my profile shows "{name}"'))
            def s2(name): pass
        """).strip())
        errors = validate_step_definitions_complete([feature, step_def])
        assert len(errors) == 1
        assert "edit my display name" in errors[0]

    def test_import_validator_works_for_any_page_path(self, tmp_path: Path):
        """Import validator just checks the filesystem — no assumed page names."""
        (tmp_path / "pages").mkdir()
        (tmp_path / "pages" / "__init__.py").write_text("")
        (tmp_path / "tests" / "step_defs").mkdir(parents=True)
        (tmp_path / "requirements.txt").write_text("pytest\n")
        (tmp_path / "pages" / "checkout_page.py").write_text("class CheckoutPage: pass")

        # Hallucinated import in a checkout context (not logout)
        step_def = gf("tests/step_defs/test_checkout.py", textwrap.dedent("""
            from pages.checkout_page import CheckoutPage  # exists — OK
            from pages.shipping_page import ShippingPage  # hallucinated — should flag
        """).strip())

        errors = validate_imports_resolvable([step_def], tmp_path)
        assert any("shipping_page" in e for e in errors)
        # The existing checkout_page import should NOT be flagged
        assert not any("checkout_page" in e and "does not exist" in e for e in errors)