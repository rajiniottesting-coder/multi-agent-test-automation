"""Step definitions for features/add_user_password_validation.feature.

Covers password policy inline validation, boundary checks, required-field
validation, confirm-password mismatch, and matching confirm-password scenarios
on the Admin > Add User form.

Rules followed:
- Every step the feature uses is declared here (module-scoped).
- Page-object methods only — no selectors in step defs.
- parsers.parse for parameterized steps.
- Boolean predicates for absence assertions (never a getter that waits).
"""
import pytest
from pytest_bdd import given, when, then, parsers, scenarios

from config.paths import feature_path

scenarios(str(feature_path("add_user_password_validation")))


# ─────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────

@pytest.fixture
def admin_add_user_page(page):
    from pages.admin_add_user_page import AdminAddUserPage
    return AdminAddUserPage(page)


@pytest.fixture
def admin_users_page(page):
    from pages.admin_users_page import AdminUsersPage
    return AdminUsersPage(page)


@pytest.fixture
def login_page(page):
    from pages.login_page import LoginPage
    return LoginPage(page)


@pytest.fixture
def menu_page(page):
    from pages.menu_page import MenuPage
    return MenuPage(page)


# ─────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────

@given("I am on the OrangeHRM login page")
def open_login_page(login_page, base_url: str) -> None:
    """Navigate to the OrangeHRM login page."""
    login_page.open(base_url)


@given(parsers.re(r'I log in as "(?P<role>[^"]*)"'))
def login_as_role(login_page, credentials, role: str) -> None:
    """Log in with real credentials resolved from the environment."""
    username, password = credentials(role)
    login_page.login_as(username, password)


@given("I am on the Add User form")
def navigate_to_add_user_form(
    menu_page,
    admin_users_page,
    admin_add_user_page,
) -> None:
    """Navigate to Admin > Users, click Add."""
    menu_page.go_to_admin()
    admin_users_page.click_add()
    assert admin_add_user_page.is_form_displayed(), "Add User form did not load"


# ─────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────

@when(parsers.parse('I enter password "{password}" on the Add User form'))
def enter_password(admin_add_user_page, password: str) -> None:
    """Type a value into the password field."""
    admin_add_user_page.enter_password(password)


@when("I click outside the password field")
def click_outside_password(admin_add_user_page) -> None:
    """Blur the password field by tabbing away."""
    admin_add_user_page.tab_away_from_password()


@when("I clear the password field on the Add User form")
def clear_password_field(admin_add_user_page) -> None:
    """Clear the password field."""
    admin_add_user_page.clear_password()


@when(parsers.parse('I enter confirm password "{password}" on the Add User form'))
def enter_confirm_password(admin_add_user_page, password: str) -> None:
    """Type a value into the confirm password field."""
    admin_add_user_page.enter_confirm_password(password)


@when("I click outside the confirm password field")
def click_outside_confirm_password(admin_add_user_page) -> None:
    """Blur the confirm password field by tabbing away."""
    admin_add_user_page.tab_away_from_confirm_password()


@when("I click into the password field and click away")
def click_password_field_and_click_away(admin_add_user_page) -> None:
    """Touch the password field and leave it empty."""
    admin_add_user_page.click_password_field()
    admin_add_user_page.tab_away_from_password()


@when("I click into the confirm password field and click away")
def click_confirm_password_field_and_click_away(admin_add_user_page) -> None:
    """Touch the confirm password field and leave it empty."""
    admin_add_user_page.click_confirm_password_field()
    admin_add_user_page.tab_away_from_confirm_password()


# ─────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────

@then(parsers.parse('I should see the password field error "{message}"'))
def assert_password_error_message(admin_add_user_page, message: str) -> None:
    """Assert a specific validation message under the Password field."""
    actual = admin_add_user_page.get_password_field_error()
    assert message in actual, (
        f"Expected '{message}' beneath Password field, got '{actual}'"
    )


@then(parsers.parse('I should see the confirm password field error "{message}"'))
def assert_confirm_password_error_message(admin_add_user_page, message: str) -> None:
    """Assert a specific validation message under the Confirm Password field."""
    actual = admin_add_user_page.get_confirm_password_field_error()
    assert message in actual, (
        f"Expected '{message}' beneath Confirm Password field, got '{actual}'"
    )


@then("I should not see a password field error")
def assert_no_password_error(admin_add_user_page) -> None:
    """Assert no error is shown under the Password field."""
    assert not admin_add_user_page.has_password_field_error(), (
        "Expected no validation message beneath the Password field, but one was found"
    )


@then("I should not see a confirm password field error")
def assert_no_confirm_password_error(admin_add_user_page) -> None:
    """Assert no error is shown under the Confirm Password field."""
    assert not admin_add_user_page.has_confirm_password_field_error(), (
        "Expected no validation message beneath the Confirm Password field, but one was found"
    )
