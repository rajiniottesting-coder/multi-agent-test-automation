"""Step definitions for features/add_user_password_validation.feature.

Covers password policy inline validation, boundary checks, required-field
validation, confirm-password mismatch, and matching confirm-password scenarios
on the Admin > Add User form.

Rules followed:
- Every step the feature uses is declared here (module-scoped).
- Page-object methods only — no selectors in step defs.
- parsers.parse for parameterized steps with non-empty values.
"""
import pytest
from pytest_bdd import given, when, then, parsers, scenarios

from config.paths import feature_path
from pages.admin_add_user_page import AdminAddUserPage
from pages.admin_users_page import AdminUsersPage
from pages.menu_page import MenuPage

scenarios(str(feature_path("add_user_password_validation")))


# ─────────────────────────────────────────────────────────────
# Fixtures (page objects not provided by conftest)
# ─────────────────────────────────────────────────────────────

@pytest.fixture
def admin_add_user_page(page) -> AdminAddUserPage:
    return AdminAddUserPage(page)


@pytest.fixture
def admin_users_page(page) -> AdminUsersPage:
    return AdminUsersPage(page)


@pytest.fixture
def menu_page(page) -> MenuPage:
    return MenuPage(page)


# ─────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────

@given("I am on the OrangeHRM login page")
def open_login_page(login_page, base_url) -> None:
    login_page.open(base_url)


@given(parsers.re(r'I log in as "(?P<role>[^"]*)"$'))
def logged_in_as_role(login_page, credentials, role: str) -> None:
    """Log in with real credentials resolved from the environment."""
    username, password = credentials(role)
    login_page.login_as(username, password)


@given("I navigate to the Add User form")
def navigate_to_add_user_form(menu_page: MenuPage, admin_users_page: AdminUsersPage, admin_add_user_page: AdminAddUserPage) -> None:
    """Navigate via Admin menu to the Add User form."""
    menu_page.go_to_admin()
    admin_users_page.click_add()
    assert admin_add_user_page.is_form_displayed(), "Add User form did not load"


# ─────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────

@when(parsers.parse('I enter password "{password}" on the Add User form'))
def enter_password(admin_add_user_page: AdminAddUserPage, password: str) -> None:
    admin_add_user_page.enter_password(password)


@when("I click outside the password field")
def click_outside_password(admin_add_user_page: AdminAddUserPage) -> None:
    admin_add_user_page.tab_away_from_password()


@when("I clear the password field on the Add User form")
def clear_password_field(admin_add_user_page: AdminAddUserPage) -> None:
    admin_add_user_page.clear_password()


@when(parsers.parse('I enter confirm password "{password}" on the Add User form'))
def enter_confirm_password(admin_add_user_page: AdminAddUserPage, password: str) -> None:
    admin_add_user_page.enter_confirm_password(password)


@when("I click outside the confirm password field")
def click_outside_confirm_password(admin_add_user_page: AdminAddUserPage) -> None:
    admin_add_user_page.tab_away_from_confirm_password()


@when("I click into the password field and click away")
def click_password_field_and_click_away(admin_add_user_page: AdminAddUserPage) -> None:
    admin_add_user_page.click_password_field()
    admin_add_user_page.tab_away_from_password()


@when("I click into the confirm password field and click away")
def click_confirm_password_field_and_click_away(admin_add_user_page: AdminAddUserPage) -> None:
    admin_add_user_page.click_confirm_password_field()
    admin_add_user_page.tab_away_from_confirm_password()


# ─────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────

@then(parsers.parse('I should see the password field error "{message}"'))
def assert_password_field_error(admin_add_user_page: AdminAddUserPage, message: str) -> None:
    actual = admin_add_user_page.get_password_field_error()
    assert message in actual, (
        f"Expected '{message}' beneath Password field, got '{actual}'"
    )


@then(parsers.parse('I should see the confirm password field error "{message}"'))
def assert_confirm_password_field_error(admin_add_user_page: AdminAddUserPage, message: str) -> None:
    actual = admin_add_user_page.get_confirm_password_field_error()
    assert message in actual, (
        f"Expected '{message}' beneath Confirm Password field, got '{actual}'"
    )


@then("I should not see a password field error")
def assert_no_password_field_error(admin_add_user_page: AdminAddUserPage) -> None:
    assert not admin_add_user_page.has_password_field_error(), (
        "Expected no validation message beneath Password field, but one was shown"
    )


@then("I should not see a confirm password field error")
def assert_no_confirm_password_field_error(admin_add_user_page: AdminAddUserPage) -> None:
    assert not admin_add_user_page.has_confirm_password_field_error(), (
        "Expected no validation message beneath Confirm Password field, but one was shown"
    )
