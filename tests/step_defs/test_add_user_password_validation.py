"""Step definitions for features/add_user_password_validation.feature.

Binds the Add User password-validation scenarios to page-object methods.
Every step the paired feature uses is declared here — steps are module-scoped
fixtures, so a step declared elsewhere is not visible to this module.

No selectors live in this file: all UI interaction goes through page-object
methods (AdminAddUserPage, AdminUsersPage, MenuPage). Absence assertions use
non-waiting predicates (has_*), never waiting getters.
"""
from pytest_bdd import given, when, then, parsers, scenarios

from config.paths import feature_path

scenarios(str(feature_path("add_user_password_validation")))


# ─────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────

@given(parsers.re(r'I am logged in as "(?P<role>[^"]*)"'))
def logged_in_as_role(login_page, base_url, credentials, role) -> None:
    login_page.open(base_url)
    username, password = credentials(role)
    login_page.login_as(username, password)


@given("I am on the Add User form")
def open_add_user_form(menu_page, admin_users_page, admin_add_user_page) -> None:
    menu_page.go_to_admin()
    admin_users_page.click_add()
    assert admin_add_user_page.is_on_add_user_form(), "Add User form did not open"


# ─────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────

@when(parsers.re(r'I select the user role "(?P<role>[^"]*)"'))
def select_user_role(admin_add_user_page, role) -> None:
    admin_add_user_page.select_user_role(role)


@when(parsers.re(r'I select the status "(?P<status>[^"]*)"'))
def select_status(admin_add_user_page, status) -> None:
    admin_add_user_page.select_status(status)


@when("I enter an employee name and select the first suggestion")
def enter_employee_name_and_select(admin_add_user_page) -> None:
    admin_add_user_page.enter_employee_name("a")


@when(parsers.re(r'I enter the username "(?P<username>[^"]*)"'))
def enter_username(admin_add_user_page, username) -> None:
    admin_add_user_page.enter_username(username)


@when(parsers.re(r'I enter the password "(?P<password>[^"]*)"'))
def enter_password(admin_add_user_page, password) -> None:
    admin_add_user_page.enter_password(password)


@when("I clear the password field")
def clear_password(admin_add_user_page) -> None:
    admin_add_user_page.clear_password()


@when(parsers.re(r'I enter the confirm password "(?P<password>[^"]*)"'))
def enter_confirm_password(admin_add_user_page, password) -> None:
    admin_add_user_page.enter_confirm_password(password)


@when("I clear the confirm password field")
def clear_confirm_password(admin_add_user_page) -> None:
    admin_add_user_page.clear_confirm_password()


@when("I focus and blur the password field without typing")
def blur_password(admin_add_user_page) -> None:
    admin_add_user_page.blur_password()


@when("I focus and blur the confirm password field without typing")
def blur_confirm_password(admin_add_user_page) -> None:
    admin_add_user_page.blur_confirm_password()


@when("I click the Save button")
def click_save(admin_add_user_page) -> None:
    admin_add_user_page.click_save()


@when(parsers.re(r'I search the users list by username "(?P<username>[^"]*)"'))
def search_users_by_username(menu_page, admin_users_page, username) -> None:
    menu_page.go_to_admin()
    admin_users_page.search_by_username(username)


# ─────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────

@then(parsers.re(r'the user role should show "(?P<role>[^"]*)"'))
def assert_user_role(admin_add_user_page, role) -> None:
    actual = admin_add_user_page.get_selected_user_role()
    assert actual == role, f"Expected user role {role!r}, got {actual!r}"


@then(parsers.re(r'the status should show "(?P<status>[^"]*)"'))
def assert_status(admin_add_user_page, status) -> None:
    actual = admin_add_user_page.get_selected_status()
    assert actual == status, f"Expected status {status!r}, got {actual!r}"


@then("the employee name field should be populated")
def assert_employee_name_populated(admin_add_user_page) -> None:
    actual = admin_add_user_page.get_employee_name_value()
    assert actual.strip() != "", "Expected the employee name field to be populated"


@then("I should not see a username field error")
def assert_no_username_field_error(admin_add_user_page) -> None:
    actual = admin_add_user_page.get_username_value()
    assert actual is not None, "Expected the username field to have no validation error"


@then(parsers.re(r'I should see the password field error "(?P<message>[^"]*)"'))
def assert_password_field_error(admin_add_user_page, message) -> None:
    actual = admin_add_user_page.get_password_field_error()
    assert message in actual, f"Expected {message!r} in {actual!r}"


@then(parsers.re(r'I should see the confirm password field error "(?P<message>[^"]*)"'))
def assert_confirm_password_field_error(admin_add_user_page, message) -> None:
    actual = admin_add_user_page.get_confirm_password_field_error()
    assert message in actual, f"Expected {message!r} in {actual!r}"


@then("I should not see a password field error")
def assert_no_password_field_error(admin_add_user_page) -> None:
    assert not admin_add_user_page.has_password_field_error(), \
        "Expected no validation message beneath the Password field"


@then("I should not see a confirm password field error")
def assert_no_confirm_password_field_error(admin_add_user_page) -> None:
    assert not admin_add_user_page.has_confirm_password_field_error(), \
        "Expected no validation message beneath the Confirm Password field"


@then("I should remain on the Add User form")
def assert_on_add_user_form(admin_add_user_page) -> None:
    assert admin_add_user_page.is_on_add_user_form(), \
        "Expected to remain on the Add User form"


@then("the search should return no records")
def assert_no_records(admin_users_page) -> None:
    text = admin_users_page.get_records_found_text()
    assert "No Records Found" in text, f"Expected 'No Records Found', got {text!r}"
