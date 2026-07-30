"""Step definitions for features/admin_add_user_password_validation.feature.

Binds the Add User password-validation scenarios to the AdminAddUserPage
page object. Steps talk to page objects through business-verb methods only.
"""
from pytest_bdd import given, when, then, parsers, scenarios

from config.paths import feature_path

scenarios(str(feature_path("admin_add_user_password_validation")))


# ─────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────

@given(parsers.re(r'I am logged in as "(?P<role>[^"]*)"'))
def login_as_role(login_page, base_url, credentials, dashboard_page, role):
    username, password = credentials(role)
    login_page.open(base_url)
    login_page.login_as(username, password)
    assert dashboard_page.is_loaded(), "Dashboard did not load after login"


@given("I am on the Add User page")
def open_add_user_page(menu_page, admin_users_page):
    menu_page.go_to("Admin")
    admin_users_page.click_add()


# ─────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────

@when(parsers.re(r'I enter the password "(?P<password>[^"]*)"'))
def enter_password(admin_add_user_page, password):
    admin_add_user_page.enter_password(password)


@when(parsers.re(r'I enter the confirm password "(?P<password>[^"]*)"'))
def enter_confirm_password(admin_add_user_page, password):
    admin_add_user_page.enter_confirm_password(password)


@when("I clear the password field")
def clear_password_field(admin_add_user_page):
    admin_add_user_page.clear_password()


@when("I clear the password fields")
def clear_password_fields(admin_add_user_page):
    admin_add_user_page.clear_password()


@when("I leave the password field empty and tab away")
def leave_password_empty(admin_add_user_page):
    admin_add_user_page.touch_password()


@when("I leave the confirm password field empty and tab away")
def leave_confirm_password_empty(admin_add_user_page):
    admin_add_user_page.touch_confirm_password()


# ─────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────

@then(parsers.parse('the password field error should be "{expected_message}"'))
def assert_password_field_error(admin_add_user_page, expected_message):
    actual = admin_add_user_page.get_password_field_error()
    assert expected_message in actual, \
        f"Expected {expected_message!r} under Password, got {actual!r}"


@then(parsers.parse('the confirm password field error should be "{expected_message}"'))
def assert_confirm_password_field_error(admin_add_user_page, expected_message):
    actual = admin_add_user_page.get_confirm_password_field_error()
    assert expected_message in actual, \
        f"Expected {expected_message!r} under Confirm Password, got {actual!r}"


@then("no password field error should be shown")
def assert_no_password_field_error(admin_add_user_page):
    assert not admin_add_user_page.has_password_field_error(), \
        "Expected no validation message under the Password field"


@then("no confirm password field error should be shown")
def assert_no_confirm_password_field_error(admin_add_user_page):
    assert not admin_add_user_page.has_confirm_password_field_error(), \
        "Expected no validation message under the Confirm Password field"
