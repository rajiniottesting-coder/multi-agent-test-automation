"""Step definitions for features/add_user_password_validation.feature.

Password-policy validation on the Admin > Add User form. Validation messages
render as the user types, so assertions run after filling a field, never after
submitting. The one Save-and-verify scenario uses a run-unique username.
"""
from pytest_bdd import given, when, then, parsers, scenarios

from config.paths import feature_path

scenarios(str(feature_path("add_user_password_validation")))


# ─────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────

@given(parsers.re(r'I am logged in as "(?P<role>[^"]*)"'))
def logged_in_as(login_page, dashboard_page, credentials, base_url, role):
    username, password = credentials(role)
    login_page.open(base_url)
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
    admin_add_user_page.blur_active_field()


@when(parsers.re(r'I enter the confirm password "(?P<password>[^"]*)"'))
def enter_confirm_password(admin_add_user_page, password):
    admin_add_user_page.clear_confirm_password()
    admin_add_user_page.enter_confirm_password(password)
    admin_add_user_page.blur_active_field()


@when("I focus and blur the password field without typing")
def focus_blur_password(admin_add_user_page):
    admin_add_user_page.focus_password()
    admin_add_user_page.blur_active_field()


@when("I focus and blur the confirm password field without typing")
def focus_blur_confirm_password(admin_add_user_page):
    admin_add_user_page.focus_confirm_password()
    admin_add_user_page.blur_active_field()


@when(parsers.re(r'I select the user role "(?P<role>[^"]*)"'))
def select_user_role(admin_add_user_page, role):
    admin_add_user_page.select_user_role(role)


@when("I select an employee from the autocomplete")
def select_employee(admin_add_user_page):
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

@then(parsers.re(r'I should see the password field error "(?P<message>[^"]*)"'))
def assert_password_field_error(admin_add_user_page, message):
    actual = admin_add_user_page.get_password_field_error()
    assert message in actual, f"Expected {message!r} in {actual!r}"


@then(parsers.re(r'I should see the confirm password field error "(?P<message>[^"]*)"'))
def assert_confirm_password_field_error(admin_add_user_page, message):
    actual = admin_add_user_page.get_confirm_password_field_error()
    assert message in actual, f"Expected {message!r} in {actual!r}"


@then("I should not see any password field error")
def assert_no_password_field_error(admin_add_user_page):
    assert not admin_add_user_page.has_password_field_error(), \
        "Expected no password field error"


@then("I should not see any confirm password field error")
def assert_no_confirm_password_field_error(admin_add_user_page):
    assert not admin_add_user_page.has_confirm_password_field_error(), \
        "Expected no confirm password field error"


@then("I should remain on the Add User form")
def assert_still_on_add_user_form(admin_add_user_page):
    assert admin_add_user_page.is_on_add_user_form(), \
        "Expected to remain on the Add User form"


@then("the users search should return no records")
def assert_no_records(admin_users_page):
    assert admin_users_page.has_no_records(), \
        "Expected the no-records indicator in the users search results"
