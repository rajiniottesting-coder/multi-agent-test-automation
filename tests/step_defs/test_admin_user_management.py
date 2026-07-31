"""Step definitions for features/admin_user_management.feature.

Binds the admin user-management scenarios to page-object methods only.
Selectors never appear here — all UI interaction goes through page objects.
Usernames created by the test are run-unique (derived from unique_username)
so the shared demo does not collide with foreign data.

The created username is remembered in a module-scoped dict shared across the
step functions of a single scenario. It is a plain module-level object rather
than a fixture, so no undeclared fixture is requested.
"""
from pytest_bdd import given, when, then, parsers, scenarios

from config.paths import feature_path

scenarios(str(feature_path("admin_user_management")))


# Per-scenario scratch space for the run-unique username. pytest-bdd runs one
# scenario at a time in a worker, so a simple module-level dict is sufficient
# to carry the value between the create step and the later search steps.
_created = {"username": ""}


# ─────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────

@given(parsers.re(r'I am logged in as "(?P<role>[^"]*)"'))
def logged_in_as(login_page, dashboard_page, credentials, base_url, role):
    username, password = credentials(role)
    login_page.open(base_url)
    login_page.login_as(username, password)
    assert dashboard_page.is_loaded(), "Dashboard did not load after login"


@given("I am on the Admin Users list")
def on_admin_users_list(admin_users_page, base_url):
    admin_users_page.open(base_url)


# ─────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────

@when("I click the Add button on the Users list")
def click_add_button(admin_users_page):
    admin_users_page.click_add()


@when(parsers.re(r'I select the user role "(?P<role>[^"]*)"'))
def select_user_role(admin_add_user_page, role):
    assert admin_add_user_page.is_loaded(), "Add User form did not load"
    admin_add_user_page.select_user_role(role)


@when(parsers.re(r'I enter an employee name starting with "(?P<letter>[^"]*)" and pick the first suggestion'))
def enter_employee_name(admin_add_user_page, letter):
    admin_add_user_page.enter_employee_name(letter)


@when(parsers.re(r'I select the status "(?P<status>[^"]*)"'))
def select_status(admin_add_user_page, status):
    admin_add_user_page.select_status(status)


@when("I enter a run-unique username")
def enter_unique_username(admin_add_user_page, unique_username):
    _created["username"] = unique_username
    admin_add_user_page.enter_username(unique_username)


@when(parsers.re(r'I enter the password "(?P<password>[^"]*)" in both password fields'))
def enter_passwords(admin_add_user_page, password):
    admin_add_user_page.enter_password(password)
    admin_add_user_page.enter_confirm_password(password)


@when("I click the Save button")
def click_save(admin_add_user_page):
    admin_add_user_page.click_save()


@when("I search the Users list for the created username")
def search_created_username(admin_users_page):
    admin_users_page.clear_search()
    admin_users_page.search_by_username(_created["username"])


@when(parsers.re(r'I search the Users list for username "(?P<username>[^"]*)"'))
def search_literal_username(admin_users_page, username):
    admin_users_page.clear_search()
    admin_users_page.search_by_username(username)


@when("I delete the created user and confirm the deletion")
def delete_and_confirm(admin_users_page):
    admin_users_page.click_row_delete()
    assert admin_users_page.is_delete_dialog_displayed(), "Delete confirmation dialog did not appear"
    admin_users_page.confirm_delete()


@when("I delete the created user and cancel the confirmation dialog")
def delete_and_cancel(admin_users_page):
    admin_users_page.click_row_delete()
    assert admin_users_page.is_delete_dialog_displayed(), "Delete confirmation dialog did not appear"
    admin_users_page.cancel_delete()


# ─────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────

@then("I should see a success toast")
def assert_success_toast(admin_add_user_page):
    toast = admin_add_user_page.get_toast_text()
    assert "Success" in toast, f"Expected a success toast, got {toast!r}"


@then(parsers.re(r'the results summary should read "(?P<expected>[^"]*)"'))
def assert_results_summary(admin_users_page, expected):
    if expected == "No Records Found":
        assert admin_users_page.has_no_records(), (
            f"Expected 'No Records Found' but summary was "
            f"{admin_users_page.get_records_found_text()!r}"
        )
    else:
        actual = admin_users_page.get_records_found_text()
        assert expected in actual, f"Expected {expected!r} in {actual!r}"


@then("the single result row should show the created username")
def assert_single_row_username(admin_users_page):
    usernames = admin_users_page.get_row_usernames()
    assert len(usernames) == 1, f"Expected exactly one row, got {usernames!r}"
    assert usernames[0] == _created["username"], (
        f"Expected row username {_created['username']!r}, got {usernames[0]!r}"
    )


@then("no success toast should be shown")
def assert_no_success_toast(admin_users_page):
    assert not admin_users_page.is_delete_dialog_displayed(), (
        "Delete confirmation dialog should have closed after cancel"
    )
    toast = admin_users_page.get_toast_text()
    assert "Success" not in toast, f"Expected no success toast, got {toast!r}"
