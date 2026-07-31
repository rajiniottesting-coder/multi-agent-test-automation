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
    7. Page-object selectors       — literals / invented inventory keys

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

from validators.gherkin_analyzer import (
    validate_filename_consistency,
    validate_feature_file_structure,
    validate_step_definitions_complete,
)
from validators.import_validator import validate_imports_resolvable
from validators.method_resolution_validator import (
    validate_method_resolution,
    validate_page_object_selectors,
)
from core.app_context import AppContext
from agents.agent2_coder import validate_paths_against_policy
from core.schemas import GeneratedFile


# Helper: build a GeneratedFile from a path and content
def gf(path: str, content: str, is_new: bool = True) -> GeneratedFile:
    return GeneratedFile(file_path=path, content=content, is_new_file=is_new, purpose="test")


# Helper: build a fake project with the same baseline as the real repo
@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    """Minimal generic web-app project layout (login + landing page baseline)."""
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

    # SomePage (RESERVED — must never be modified)
    (tmp_path / "pages" / "login_page.py").write_text(textwrap.dedent("""
        from pages.base_page import BasePage

        class SomePage(BasePage):
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
# 2. Gherkin structure (PR #14 regression — orphan And step at line 10)
# =============================================================================
class TestFeatureFileStructure:
    """Every step keyword (Given/When/Then/And/But/*) must be inside a
    Scenario, Scenario Outline, Background, Examples, or Rule block. Steps
    appearing at the top level of the .feature file cause pytest-bdd to
    fail at collection time with `FeatureError: Step definition outside of
    a Scenario or a Background.`
    """

    def test_well_formed_feature_passes(self):
        feature = gf("features/x.feature", textwrap.dedent("""
            Feature: x
              Background:
                Given I am logged in
              Scenario: y
                When I click button
                Then I see result
        """).strip())
        assert validate_feature_file_structure([feature]) == []

    def test_orphan_and_step_caught_pr14_regression(self):
        """The exact shape of the PR #14 failure: an `And` step floating
        between Background and Scenario blocks, outside any container."""
        feature = gf("features/dashboard_menu_and_logout.feature", textwrap.dedent("""
            Feature: Dashboard menu and logout

              Background:
                Given I am logged in as "valid_user"
                When I navigate to the dashboard page
                Then I should see the dashboard widgets

              And I should see the page title "Dashboard"

              Scenario: Verify burger menu present
                Then I should see the burger menu icon
        """).strip())
        errors = validate_feature_file_structure([feature])
        assert len(errors) == 1
        # Error must reference the offending line and the FeatureError
        assert "outside any" in errors[0]
        assert "I should see the page title" in errors[0]
        assert "pytest-bdd" in errors[0]

    def test_orphan_given_at_top_level(self):
        feature = gf("features/x.feature", textwrap.dedent("""
            Feature: x
              Given some orphaned setup

              Scenario: y
                When I do x
        """).strip())
        errors = validate_feature_file_structure([feature])
        assert len(errors) == 1
        assert "Given some orphaned setup" in errors[0]

    def test_scenario_outline_examples_table_accepted(self):
        """Steps inside Scenario Outline + its Examples: data table
        (which contains | rows) must NOT be flagged as orphans."""
        feature = gf("features/x.feature", textwrap.dedent("""
            Feature: x
              Scenario Outline: parametrized
                Given I am logged in as "<user>"
                When I do something
                Then I see "<result>"
              Examples:
                | user      | result  |
                | alice     | OK      |
                | bob       | FAIL    |
        """).strip())
        assert validate_feature_file_structure([feature]) == []

    def test_rule_block_accepted(self):
        """Gherkin 6+ Rule blocks contain Scenarios and are valid containers."""
        feature = gf("features/x.feature", textwrap.dedent("""
            Feature: x
              Rule: y
                Scenario: z
                  Given I am here
                  Then I see something
        """).strip())
        assert validate_feature_file_structure([feature]) == []

    def test_only_inspects_feature_files(self):
        """Non-.feature files are ignored even if they look Gherkin-ish."""
        not_a_feature = gf("docs/x.md", "Given a markdown doc\nWhen reading\nThen no error")
        assert validate_feature_file_structure([not_a_feature]) == []


# =============================================================================
# 3. Step coverage (PR #9 — missing decorators)
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

    def test_steps_from_sibling_step_def_in_batch_pooled(self):
        """When the LLM splits steps across two generated step-def files
        (e.g. shared steps in test_shared.py, feature-specific steps in
        test_x.py), both files should be pooled when checking coverage —
        otherwise we get false positives. Regresses the SCRUM-20 family
        of bugs where the validator only inspected the paired file."""
        feature = gf("features/x.feature", textwrap.dedent("""
            Feature: x
              Scenario: y
                Given common setup step
                When specific action happens
        """).strip())
        paired = gf("tests/step_defs/test_x.py", textwrap.dedent("""
            from pytest_bdd import when
            @when("specific action happens")
            def s1(): pass
        """).strip())
        sibling = gf("tests/step_defs/test_shared.py", textwrap.dedent("""
            from pytest_bdd import given
            @given("common setup step")
            def s2(): pass
        """).strip())
        # project_root=None disables on-disk scan so we test the batch-pool
        # path in isolation.
        errors = validate_step_definitions_complete(
            [feature, paired, sibling], project_root=None
        )
        assert errors == [], errors

    def test_steps_in_sibling_module_are_NOT_pooled(self, tmp_path):
        """ADR-013: a step declared in a SIBLING step-def module is not
        visible at runtime (pytest-bdd steps are module-scoped fixtures), so
        the validator must report it as missing. Pooling siblings previously
        let this pass here and fail at collection with
        StepDefinitionNotFoundError."""
        step_defs_dir = tmp_path / "tests" / "step_defs"
        step_defs_dir.mkdir(parents=True)
        (step_defs_dir / "test_login.py").write_text(textwrap.dedent("""
            from pytest_bdd import when, parsers
            @when(parsers.parse('I log in as "{user}"'))
            def s2(user): pass
        """).strip())

        feature = gf("features/logout.feature", textwrap.dedent("""
            Feature: Logout
              Scenario: Logout works
                When I log in as "alice"
        """).strip())
        step_def = gf("tests/step_defs/test_logout.py",
                      "from pytest_bdd import when\n")

        errors = validate_step_definitions_complete(
            [feature, step_def], project_root=str(tmp_path))
        assert len(errors) == 1
        assert "I log in as" in errors[0]

    def test_steps_from_conftest_are_pooled(self, tmp_path):
        """conftest.py IS shared by pytest, so steps declared there are
        genuinely available and must NOT be reported missing."""
        step_defs_dir = tmp_path / "tests" / "step_defs"
        step_defs_dir.mkdir(parents=True)
        (step_defs_dir / "conftest.py").write_text(textwrap.dedent("""
            from pytest_bdd import given
            @given("I am on the login page")
            def s1(): pass
        """).strip())

        feature = gf("features/logout.feature", textwrap.dedent("""
            Feature: Logout
              Scenario: Logout works
                Given I am on the login page
                When I click the logout button
        """).strip())
        step_def = gf("tests/step_defs/test_logout.py", textwrap.dedent("""
            from pytest_bdd import when
            @when("I click the logout button")
            def s4(): pass
        """).strip())

        errors = validate_step_definitions_complete(
            [feature, step_def], project_root=str(tmp_path))
        assert errors == []

    def test_genuinely_missing_step_still_caught_with_disk_pool(self, tmp_path):
        """Negative control: pooling on-disk decorators must NOT mask real
        missing steps. If a step exists in neither the batch nor on disk,
        it should still surface as an error."""
        step_defs_dir = tmp_path / "tests" / "step_defs"
        step_defs_dir.mkdir(parents=True)
        (step_defs_dir / "test_login.py").write_text(
            'from pytest_bdd import given\n'
            '@given("I am on the login page")\n'
            'def f(): pass\n'
        )

        feature = gf("features/x.feature", textwrap.dedent("""
            Feature: x
              Scenario: y
                Given I am on the login page
                When I do something nobody defined anywhere
        """).strip())
        step_def = gf("tests/step_defs/test_x.py",
                      "from pytest_bdd import scenarios\n")

        errors = validate_step_definitions_complete(
            [feature, step_def], project_root=tmp_path
        )
        assert any("nobody defined anywhere" in e for e in errors), (
            f"Expected the missing step to be reported, got: {errors}"
        )


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
        # Pass a non-existent project_root so the validator skips the
        # on-disk step-def scan. Otherwise tests/step_defs/*.py on disk
        # might contain a matching parsers.re decorator that pools into
        # the available decorators and masks the in-batch issue. This
        # keeps the test isolated to the in-memory batch.
        errors = validate_step_definitions_complete(
            [feature, step_def], project_root=Path("/nonexistent_project_root")
        )

        # The `parse` library fixed empty quoted value matching in v1.22.1+.
        # Probe the actual runtime behavior so this test is resilient to
        # whatever parse version is installed (no version pinning required).
        from parse import parse as _parse_fn
        probe = _parse_fn(
            'I log in with username "{u}" and password "{p}"',
            'I log in with username "" and password "secret"',
        )
        if probe is None:
            # Old parse behavior (< 1.22.1): empty "" doesn't match at
            # runtime → validator MUST flag this with a parsers.re hint.
            assert len(errors) == 1
            assert "parsers.re" in errors[0], (
                "Error must hint parsers.re as the fix"
            )
        else:
            # New parse behavior (>= 1.22.1): empty "" matches correctly
            # at runtime → validator should report no errors.
            assert errors == [], (
                f"parse library matches empty quoted values in this "
                f"version, so validator should report 0 errors, got: {errors}"
            )

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
        # Same isolation as above — don't let on-disk files affect this test.
        assert validate_step_definitions_complete(
            [feature, step_def], project_root=Path("/nonexistent_project_root")
        ) == []


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
            from pages.login_page import SomePage
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
        """SomePage is reserved (read from disk). The LLM calls a method
        that doesn't exist on it. Must be caught."""
        step_def = gf("tests/step_defs/test_logout.py", textwrap.dedent("""
            import pytest
            from pytest_bdd import then
            from pages.login_page import SomePage

            @pytest.fixture
            def login_page(page):
                return SomePage(page)

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
        # Build a banking-style project from scratch (independent of the default baseline)
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


# ─────────────────────────────────────────────────────────────────────────
# 7. Page-object selectors
# ─────────────────────────────────────────────────────────────────────────

# A synthetic app, exactly as in tests/unit/test_page_object_selectors.py:
# these tests exercise the RULE, never the application under test.
_INV = {
    "pages": {
        "widgets": {
            "elements": {"add_button": "role=button[name='Add']",
                         "rows": ".row"},
        },
        "login": {"elements": {"username": "#u"}},
    }
}

# Same synthetic app, now with the family classification the inventory carries.
_INV_MM = {
    "pages": {
        "widgets": {
            "elements": {"add_button": "#add", "rows": ".row",
                         "rows_first": ".row >> nth=0", "opt": ".opt",
                         "cell": ".cell"},
            "multi_match": ["rows", "opt"],
            # `opt` is populated asynchronously: index 0 can be a loading row.
            "async_family": ["opt"],
        }
    }
}


def _widgets_page(body: str):
    return gf("pages/widgets_page.py",
              "from pages.base_page import BasePage\n\n\n"
              "class WidgetsPage(BasePage):\n"
              "    INVENTORY_PAGE = \"widgets\"\n\n" + body)


class TestPageObjectSelectors:
    """SCRUM-104: Agent 2 shipped a page object holding four raw CSS literals.

    The rule was enforced only by tests/unit/test_page_object_selectors.py,
    which runs in Agent 4 — after the LLM spend, after the PR, and reported
    against the story instead of the generation that caused it. These tests
    lock the same rule into the generation-time gate.
    """

    def test_literal_selectors_in_a_page_object_are_caught(self, project_root: Path):
        """The exact SCRUM-104 shape: selectors as class constants."""
        page_obj = gf("pages/widgets_page.py", textwrap.dedent("""
            from pages.base_page import BasePage

            class WidgetsPage(BasePage):
                INVENTORY_PAGE = "widgets"

                ROW_DELETE_ICON = ".row .icon.bi-trash"
                DELETE_DIALOG = ".dialog-container-default"

                def click_add(self) -> None:
                    self.click(self.sel("add_button"))
        """).strip())
        errors = validate_page_object_selectors([page_obj], project_root, inventory=_INV)
        assert len(errors) == 2
        assert all("Selector inventory error" in e for e in errors)
        assert any("ROW_DELETE_ICON" in e for e in errors)
        assert any("DELETE_DIALOG" in e for e in errors)

    def test_invented_inventory_key_is_caught(self, project_root: Path):
        """The other escape route: a key the inventory does not have."""
        page_obj = gf("pages/widgets_page.py", textwrap.dedent("""
            from pages.base_page import BasePage

            class WidgetsPage(BasePage):
                INVENTORY_PAGE = "widgets"

                def delete(self) -> None:
                    self.click(self.sel("row_delete_icon"))
        """).strip())
        errors = validate_page_object_selectors([page_obj], project_root, inventory=_INV)
        assert len(errors) == 1
        assert "row_delete_icon" in errors[0]
        assert "add_button" in errors[0]     # names what IS available

    def test_missing_inventory_page_is_caught(self, project_root: Path):
        page_obj = gf("pages/widgets_page.py", textwrap.dedent("""
            from pages.base_page import BasePage

            class WidgetsPage(BasePage):
                def click_add(self) -> None:
                    self.click(self.sel("add_button"))
        """).strip())
        errors = validate_page_object_selectors([page_obj], project_root, inventory=_INV)
        assert len(errors) == 1
        assert "INVENTORY_PAGE" in errors[0]

    def test_unknown_inventory_page_is_caught(self, project_root: Path):
        page_obj = gf("pages/widgets_page.py", textwrap.dedent("""
            from pages.base_page import BasePage

            class WidgetsPage(BasePage):
                INVENTORY_PAGE = "nowhere"

                def click_add(self) -> None:
                    self.click(self.sel("add_button"))
        """).strip())
        errors = validate_page_object_selectors([page_obj], project_root, inventory=_INV)
        assert len(errors) == 1
        assert "nowhere" in errors[0]

    def test_a_clean_page_object_passes(self, project_root: Path):
        """Including a docstring that SHOWS a selector while teaching the rule."""
        page_obj = gf("pages/widgets_page.py", textwrap.dedent("""
            from pages.base_page import BasePage

            class WidgetsPage(BasePage):
                \"\"\"Selectors come from the inventory, never as ".some-class".\"\"\"

                INVENTORY_PAGE = "widgets"

                # BAD = ".never-do-this"
                def click_add(self) -> None:
                    self.click(self.sel("add_button"))
        """).strip())
        assert validate_page_object_selectors([page_obj], project_root, inventory=_INV) == []

    def test_only_page_objects_are_scanned(self, project_root: Path):
        """Step defs and base_page.py are out of scope for this validator."""
        step_def = gf("tests/step_defs/test_widgets.py", 'SEL = ".row .icon"')
        base = gf("pages/base_page.py", 'SEL = ".row .icon"')
        assert validate_page_object_selectors([step_def, base], project_root, inventory=_INV) == []

    def test_computed_selector_key_is_not_guessed_at(self, project_root: Path):
        """An f-string key is unknowable statically — never a false accusation."""
        page_obj = gf("pages/widgets_page.py", textwrap.dedent("""
            from pages.base_page import BasePage

            class WidgetsPage(BasePage):
                INVENTORY_PAGE = "widgets"

                def click_row(self, name: str) -> None:
                    self.click(self.sel(f"row_{name}"))
        """).strip())
        assert validate_page_object_selectors([page_obj], project_root, inventory=_INV) == []

    def test_unparseable_page_object_still_reports_its_literals(self, project_root: Path):
        """A syntax error must not swallow the literal it sits next to."""
        page_obj = gf("pages/widgets_page.py", 'SEL = ".row"\ndef broken(:')
        errors = validate_page_object_selectors([page_obj], project_root, inventory=_INV)
        assert len(errors) == 1
        assert "literal selector" in errors[0]

    def test_unreadable_inventory_degrades_to_the_literal_scan(self, project_root: Path):
        """No inventory in this environment: still catch literals, claim nothing else."""
        page_obj = gf("pages/widgets_page.py", textwrap.dedent("""
            from pages.base_page import BasePage

            class WidgetsPage(BasePage):
                INVENTORY_PAGE = "widgets"
                SEL = ".row"

                def go(self) -> None:
                    self.click(self.sel("not_a_real_key"))
        """).strip())
        errors = validate_page_object_selectors([page_obj], project_root, inventory={})
        assert len(errors) == 1
        assert "literal selector" in errors[0]

    def test_empty_batch_is_clean(self, project_root: Path):
        assert validate_page_object_selectors([], project_root, inventory=_INV) == []

    def test_windows_paths_are_scanned_too(self, project_root: Path):
        page_obj = gf("pages\\widgets_page.py", 'SEL = ".row"')
        assert len(validate_page_object_selectors([page_obj], project_root, inventory=_INV)) == 1


def _configured_inventory() -> dict:
    """The inventory this checkout is pointed at, per config.yaml.

    Read through the config rather than naming a file: these two assertions
    are about THIS checkout's inventory, whichever app it holds, so swapping
    the app under test must not break the framework's own suite.
    """
    import json
    import yaml
    repo = Path(__file__).resolve().parents[2]
    cfg = yaml.safe_load((repo / "config" / "config.yaml").read_text(encoding="utf-8"))
    rel = (cfg.get("app_under_test") or {}).get("inventory_file")
    return json.loads((repo / rel).read_text(encoding="utf-8"))


class TestMultiMatchEnforcement:
    """SCRUM-104 again, one layer up.

    The first fix stopped page objects inventing selectors. It did not stop
    them using a legitimate inventory key that happens to match a whole family
    - one option-family selector matched three options and Playwright's strict mode
    raised on it. The inventory now says which keys are families; this makes
    that machine-checkable instead of a prose note someone has to remember.
    """

    def test_clicking_a_family_key_is_rejected(self, project_root: Path):
        errors = validate_page_object_selectors(
            [_widgets_page("    def go(self) -> None:\n"
                           "        self.click(self.sel('rows'))\n")],
            project_root, inventory=_INV_MM)
        assert len(errors) == 1
        assert "multi_match" in errors[0]
        assert "strict mode violation" in errors[0]

    def test_waiting_on_a_family_key_is_rejected(self, project_root: Path):
        errors = validate_page_object_selectors(
            [_widgets_page("    def go(self) -> None:\n"
                           "        self.wait_visible(self.sel('opt'))\n")],
            project_root, inventory=_INV_MM)
        assert len(errors) == 1

    def test_the_error_names_an_existing_first_sibling(self, project_root: Path):
        errors = validate_page_object_selectors(
            [_widgets_page("    def go(self) -> None:\n"
                           "        self.click(self.sel('rows'))\n")],
            project_root, inventory=_INV_MM)
        assert "rows_first" in errors[0]

    def test_an_async_family_is_never_offered_an_index_pin(self, project_root: Path):
        """SCRUM-104, 31 Jul 2026. `autocomplete_option_first` (>> nth=0) was
        added as the 'safe' way to pick a suggestion. The app renders a loading
        row while its request is in flight, so nth=0 WAS that placeholder:
        waiting for it succeeded, clicking it selected nothing, the form was
        refused client-side with no request sent, and the test failed three
        steps later on a confirmation that never existed. An index pin is
        only ever valid for a STATIC family.
        """
        errors = validate_page_object_selectors(
            [_widgets_page("    def go(self) -> None:\n"
                           "        self.click(self.sel('opt'))\n")],
            project_root, inventory=_INV_MM)
        assert len(errors) == 1
        assert "BY ITS TEXT" in errors[0]
        assert "select_custom_option" in errors[0]
        assert "opt_first" in errors[0] and "NEVER" in errors[0]
        assert "loading placeholder" in errors[0]

    def test_a_static_family_still_gets_its_index_pin(self, project_root: Path):
        """The async rule must not swallow the ordinary case."""
        errors = validate_page_object_selectors(
            [_widgets_page("    def go(self) -> None:\n"
                           "        self.click(self.sel('rows'))\n")],
            project_root, inventory=_INV_MM)
        assert "rows_first" in errors[0]
        assert "BY ITS TEXT" not in errors[0]

    def test_async_family_absent_or_malformed_is_a_no_op(self, project_root: Path):
        """An inventory predating the field keeps its old behaviour."""
        inv = {"pages": {"widgets": {
            "elements": {"opt": ".opt", "opt_first": ".opt >> nth=0"},
            "multi_match": ["opt"], "async_family": "opt"}}}   # a string, not a list
        errors = validate_page_object_selectors(
            [_widgets_page("    def go(self) -> None:\n"
                           "        self.click(self.sel('opt'))\n")],
            project_root, inventory=inv)
        assert "opt_first" in errors[0]
        assert "BY ITS TEXT" not in errors[0]

    def test_plural_reads_are_still_allowed_on_an_async_family(self, project_root: Path):
        """Listing what an autocomplete offered is legitimate."""
        assert validate_page_object_selectors(
            [_widgets_page("    def go(self):\n"
                           "        return self.get_all_texts(self.sel('opt'))\n")],
            project_root, inventory=_INV_MM) == []

    def test_no_async_family_may_carry_an_index_pinned_sibling(self):
        """Guards the real inventory: a `<key>_first` for an async family is
        the exact defect this fix removed, and must not creep back."""
        inv = _configured_inventory()
        for page, entry in inv["pages"].items():
            for key in entry.get("async_family") or []:
                assert f"{key}_first" not in entry["elements"], (
                    f"{page}.{key} is async - an index pin cannot be correct")

    def test_every_async_family_is_also_declared_multi_match(self):
        """async_family is a refinement of multi_match, never a separate set."""
        inv = _configured_inventory()
        for page, entry in inv["pages"].items():
            families = set(entry.get("multi_match") or [])
            for key in entry.get("async_family") or []:
                assert key in families, f"{page}.{key} async but not multi_match"

    def test_the_error_never_tells_the_model_to_invent_a_key(self, project_root: Path):
        """SCRUM-103, 31 Jul 2026: the remedy used to read "add a '<key>_first'
        key to the inventory". The model cannot edit the inventory and rule 15
        forbids inventing keys, so it wrote self.sel('autocomplete_option_first')
        for a key that did not exist and the run died on the next check. The
        remedy must only ever name actions the model is allowed to take.
        """
        inv = {"pages": {"widgets": {"elements": {"opt": ".opt"},
                                     "multi_match": ["opt"]}}}
        errors = validate_page_object_selectors(
            [_widgets_page("    def go(self) -> None:\n"
                           "        self.click(self.sel('opt'))\n")],
            project_root, inventory=inv)
        assert "add a 'opt_first' key" not in errors[0]
        assert "Do NOT write self.sel('opt_first')" in errors[0]
        assert "select_custom_option" in errors[0]
        assert "`notes`" in errors[0]

    @pytest.mark.parametrize("call", [
        "return self.get_all_texts(self.sel('opt'))",
        "return self.get_count(self.sel('rows'))",
        "return self.exists(self.sel('rows'))",
        "return self.get_nth_text(self.sel('opt'), 1)",
        "return self.get_row_count(self.sel('rows'))",
        "return self.find_row_index_by_text(self.sel('rows'), 'x')",
        "return self.get_cell_text(self.sel('rows'), 0, self.sel('cell'))",
    ])
    def test_plural_reads_are_allowed(self, project_root: Path, call: str):
        """A family selector is exactly what these helpers are for."""
        assert validate_page_object_selectors(
            [_widgets_page(f"    def go(self):\n        {call}\n")],
            project_root, inventory=_INV_MM) == []

    def test_the_first_sibling_is_allowed(self, project_root: Path):
        assert validate_page_object_selectors(
            [_widgets_page("    def go(self) -> None:\n"
                           "        self.click(self.sel('rows_first'))\n")],
            project_root, inventory=_INV_MM) == []

    def test_a_single_key_is_untouched(self, project_root: Path):
        assert validate_page_object_selectors(
            [_widgets_page("    def go(self) -> None:\n"
                           "        self.click(self.sel('add_button'))\n")],
            project_root, inventory=_INV_MM) == []

    def test_page_dot_locator_is_strict_too(self, project_root: Path):
        """Reaching past BasePage does not escape strict mode."""
        errors = validate_page_object_selectors(
            [_widgets_page("    def go(self) -> None:\n"
                           "        self.page.locator(self.sel('rows')).click()\n")],
            project_root, inventory=_INV_MM)
        assert len(errors) == 1

    def test_composing_the_family_key_is_still_caught(self, project_root: Path):
        """f-string narrowing is rule 13's problem and this one's too."""
        errors = validate_page_object_selectors(
            [_widgets_page('    def go(self) -> None:\n'
                           '        self.click(f"{self.sel(\'rows\')} >> nth=0")\n')],
            project_root, inventory=_INV_MM)
        assert len(errors) == 1

    def test_each_violation_is_reported_once(self, project_root: Path):
        errors = validate_page_object_selectors(
            [_widgets_page("    def a(self) -> None:\n"
                           "        self.click(self.sel('rows'))\n\n"
                           "    def b(self) -> None:\n"
                           "        self.fill(self.sel('opt'), 'x')\n")],
            project_root, inventory=_INV_MM)
        assert len(errors) == 2

    def test_a_key_held_in_a_variable_is_not_guessed_at(self, project_root: Path):
        """Static tracing stops here on purpose - a false accusation would send
        the repair loop rewriting correct code."""
        assert validate_page_object_selectors(
            [_widgets_page("    def go(self) -> None:\n"
                           "        s = self.sel('rows')\n"
                           "        self.click(s)\n")],
            project_root, inventory=_INV_MM) == []

    @pytest.mark.parametrize("mm", [None, "rows", 0, {}, [], ["ghost"]])
    def test_absent_or_malformed_classification_is_a_no_op(self, project_root: Path, mm):
        """An inventory that predates the field, or carries junk in it, must
        keep working - never harden into a source of false failures."""
        inv = {"pages": {"widgets": {"elements": {"rows": ".row"},
                                     "multi_match": mm}}}
        assert validate_page_object_selectors(
            [_widgets_page("    def go(self) -> None:\n"
                           "        self.click(self.sel('rows'))\n")],
            project_root, inventory=inv) == []

    def test_the_real_inventory_classifies_its_own_families(self):
        """Every committed page that has a table or an options list should
        declare it. Guards against a new page shipping unclassified."""
        inv = _configured_inventory()
        # Key names that are families in any app that uses them, by meaning.
        known_families = ("table_rows", "dropdown_option", "autocomplete_option",
                          "field_error", "side_menu_items", "list_items")
        for page, entry in inv["pages"].items():
            families = set(entry.get("multi_match") or [])
            for key in entry["elements"]:
                if key in known_families:
                    assert key in families, f"{page}.{key} is a family but unlisted"

    def test_every_declared_family_exists_as_an_element(self):
        """A typo in multi_match would silently protect nothing."""
        inv = _configured_inventory()
        for page, entry in inv["pages"].items():
            for key in entry.get("multi_match") or []:
                assert key in entry["elements"], f"{page}.multi_match names unknown {key!r}"