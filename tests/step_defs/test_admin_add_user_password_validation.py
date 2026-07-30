"""Step definitions for features/admin_add_user_password_validation.feature.

Implements all Given/When/Then steps for password and confirm-password
inline validation on the Admin > Add User form.

Rules followed:
- Every step the feature file uses is declared here (module-scoped).
- Page-object methods only — no selectors in step defs.
- parsers.re used where empty quoted values are possible.
- parsers.parse used where values are always non-empty.
"""
from pytest_bdd import given, when, then, parsers, scenarios

from config.paths import feature_path

scenarios(str(feature_path("admin_add_user_password_validation")))


# ─────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────

@given("I am on the OrangeHRM login page")
def open_login_page(login_page, base_url) -> None:
    login_page.open(base_url)


@given(parsers.re(r'I log in as "(?P<role>[^"]*)"'))
def given_log_in_as(login_page, credentials, role: str) -> None:
    """Log in with real credentials resolved from the environment."""
    username, password = credentials(role)
    login_page.login_as(username, password)


@given("I navigate to the Admin Add User page")
def navigate_to_admin_add_user(menu_page, admin_users_page, admin_add_user_page) -> None:
    """Navigate via menu to Admin > Users > Add."""
    menu_page.go_to("Admin")
    admin_users_page.click_add()
    assert admin_add_user_page.is_loaded(), "Add User form did not load"


# ─────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────

@when(parsers.re(r'I enter password "(?P<password>[^"]*)" in the add user form'))
def enter_password(admin_add_user_page, password: str) -> None:
    """Type a value into the Password field."""
    admin_add_user_page.enter_password(password)


@when(parsers.re(r'I enter confirm password "(?P<password>[^"]*)" in the add user form'))
def enter_confirm_password(admin_add_user_page, password: str) -> None:
    """Type a value into the Confirm Password field."""
    admin_add_user_page.enter_confirm_password(password)


@when("I click outside the password field")
def click_outside_password(admin_add_user_page) -> None:
    """Tab away from the Password field to trigger validation."""
    admin_add_user_page.tab_away_from_password()


@when("I click outside the confirm password field")
def click_outside_confirm_password(admin_add_user_page) -> None:
    """Tab away from the Confirm Password field to trigger validation."""
    admin_add_user_page.tab_away_from_confirm_password()


@when("I clear the password field in the add user form")
def clear_password(admin_add_user_page) -> None:
    """Clear the Password field."""
    admin_add_user_page.clear_password()


@when("I click into the password field without typing and click outside")
def focus_password_and_tab(admin_add_user_page) -> None:
    """Focus the Password field and tab away without typing."""
    admin_add_user_page.focus_password()
    admin_add_user_page.tab_away_from_password()


@when("I click into the confirm password field without typing and click outside")
def focus_confirm_password_and_tab(admin_add_user_page) -> None:
    """Focus the Confirm Password field and tab away without typing."""
    admin_add_user_page.focus_confirm_password()
    admin_add_user_page.tab_away_from_confirm_password()


@when("I click into the password field and click away")
def click_into_password_and_away(admin_add_user_page) -> None:
    """Click into the Password field then click away to trigger required validation."""
    admin_add_user_page.focus_password()
    admin_add_user_page.tab_away_from_password()


@when("I click into the confirm password field and click away")
def click_into_confirm_password_and_away(admin_add_user_page) -> None:
    """Click into the Confirm Password field then click away to trigger required validation."""
    admin_add_user_page.focus_confirm_password()
    admin_add_user_page.tab_away_from_confirm_password()


# ─────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────

@then(parsers.re(r'I should see the password validation message "(?P<expected_message>[^"]*)"'))
def assert_password_error(admin_add_user_page, expected_message: str) -> None:
    """Assert that the expected validation message appears under the Password field."""
    admin_add_user_page.wait_for_field_error(expected_message, timeout_ms=5000)
    actual = admin_add_user_page.get_password_field_error()
    assert expected_message in actual, (
        f"Expected password error {expected_message!r}, got {actual!r}"
    )


@then(parsers.re(r'I should see the confirm password validation message "(?P<expected_message>[^"]*)"'))
def assert_confirm_password_error(admin_add_user_page, expected_message: str) -> None:
    """Assert that the expected validation message appears under the Confirm Password field."""
    admin_add_user_page.wait_for_field_error(expected_message, timeout_ms=5000)
    actual = admin_add_user_page.get_confirm_password_field_error()
    assert expected_message in actual, (
        f"Expected confirm password error {expected_message!r}, got {actual!r}"
    )


@then("I should see no password validation message")
def assert_no_password_error(admin_add_user_page) -> None:
    """Assert that no validation message is shown under the Password field."""
    admin_add_user_page.wait_for_no_field_error(timeout_ms=3000)
    error = admin_add_user_page.get_password_field_error()
    assert error == "", (
        f"Expected no password error but found {error!r}"
    )


@then("I should see no confirm password validation message")
def assert_no_confirm_password_error(admin_add_user_page) -> None:
    """Assert that no validation message is shown under the Confirm Password field."""
    admin_add_user_page.wait_for_no_field_error(timeout_ms=3000)
    error = admin_add_user_page.get_confirm_password_field_error()
    assert error == "", (
        f"Expected no confirm password error but found {error!r}"
    )


@then("I should not see any password validation message")
def assert_not_any_password_validation_message(admin_add_user_page) -> None:
    """Assert that no validation message is shown under the Password field (alternate phrasing)."""
    admin_add_user_page.wait_for_no_field_error(timeout_ms=3000)
    error = admin_add_user_page.get_password_field_error()
    assert error == "", (
        f"Expected no password validation message but found {error!r}"
    )
