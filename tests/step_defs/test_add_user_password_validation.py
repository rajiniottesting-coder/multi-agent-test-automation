"""Step definitions for features/add_user_password_validation.feature.

Binds the Add User password-validation scenarios to page-object methods.
All UI interaction goes through AdminAddUserPage / AdminUsersPage methods;
no selectors appear in this file.
"""
from pytest_bdd import given, when, then, parsers, scenarios

from config.paths import feature_path

scenarios(str(feature_path("add_user_password_validation")))


# ─────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────

@given(parsers.re(r'I am logged in as "(?P<role>[^"]*)"'))
def logged_in_as(login_page, dashboard_page, credentials, role):
    username, password = credentials(role)
    login_page.login_as(username, password)
    assert dashboard_page.is_loaded(), "Dashboard did not load after login"


@given("I am on the Add User form")
def on_add_user_form(admin_users_page, admin_add_user_page, base_url):
    admin_users_page.open(base_url)
    admin_users_page.click_add()
    assert admin_add_user_page.is_on_add_user_form(), "Add User form did not open"


# ─────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────

@when(parsers.re(r'I enter the password "(?P<password>[^"]*)"'))
def enter_password(admin_add_user_page, password):
    admin_add_user_page.clear_password()
    admin_add_user_page.enter_password(password)
    admin_add_user_page.blur_password()


@when(parsers.re(r'I enter the confirm password "(?P<password>[^"]*)"'))
def enter_confirm_password(admin_add_user_page, password):
    admin_add_user_page.clear_confirm_password()
    admin_add_user_page.enter_confirm_password(password)
    admin_add_user_page.blur_confirm_password()


@when("I focus and blur the password field without typing")
def focus_blur_password(admin_add_user_page):
    admin_add_user_page.focus_password()
    admin_add_user_page.blur_password()


@when("I focus and blur the confirm password field without typing")
def focus_blur_confirm_password(admin_add_user_page):
    admin_add_user_page.focus_confirm_password()
    admin_add_user_page.blur_confirm_password()


@when(parsers.re(r'I select the user role "(?P<role>[^"]*)"'))
def select_user_role(admin_add_user_page, role):
    admin_add_user_page.select_user_role(role)


@when("I enter an employee name and pick the first suggestion")
def enter_employee_name(admin_add_user_page):
    admin_add_user_page.enter_employee_name("a")


@when(parsers.re(r'I select the status "(?P<status>[^"]*)"'))
def select_status(admin_add_user_page, status):
    admin_add_user_page.select_status(status)


@when(parsers.re(r'I enter the username "(?P<username>[^"]*)"'))
def enter_username(admin_add_user_page, username):
    admin_add_user_page.enter_username(username)


@when("I click the Save button")
def click_save(admin_add_user_page):
    admin_add_user_page.click_save()


@when(parsers.re(r'I search the users list for username "(?P<username>[^"]*)"'))
def search_users(admin_users_page, base_url, username):
    admin_users_page.open(base_url)
    admin_users_page.search_by_username(username)


# ─────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────

@then(parsers.re(r'I should see the password field error "(?P<expected>[^"]*)"'))
def assert_password_field_error(admin_add_user_page, expected):
    actual = admin_add_user_page.get_password_field_error()
    assert expected in actual, f"Expected {expected!r} in {actual!r}"


@then(parsers.re(r'I should see the confirm password field error "(?P<expected>[^"]*)"'))
def assert_confirm_password_field_error(admin_add_user_page, expected):
    actual = admin_add_user_page.get_confirm_password_field_error()
    assert expected in actual, f"Expected {expected!r} in {actual!r}"


@then("I should not see any password field error")
def assert_no_password_field_error(admin_add_user_page):
    assert not admin_add_user_page.has_password_field_error(), \
        "Expected no password field error to be shown"


@then("I should not see any confirm password field error")
def assert_no_confirm_password_field_error(admin_add_user_page):
    assert not admin_add_user_page.has_confirm_password_field_error(), \
        "Expected no confirm password field error to be shown"


@then("I should remain on the Add User form")
def assert_remain_on_add_user_form(admin_add_user_page):
    assert admin_add_user_page.is_on_add_user_form(), \
        "Expected to remain on the Add User form"


@then("the users search should return no records")
def assert_no_records(admin_users_page):
    count = admin_users_page.get_record_count()
    assert count == 0, f"Expected no records, got {count}"
