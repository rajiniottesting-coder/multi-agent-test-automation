"""Step definitions for features/admin_user_lifecycle.feature.

Binds the admin-user-lifecycle scenarios to the Admin page objects. Steps
interact with the UI exclusively through page-object methods; no selector,
locator, or DOM query ever appears here. Run-unique usernames are derived
from the `unique_username` fixture so the shared demo cannot collide.
"""
from pytest_bdd import given, when, then, parsers, scenarios

from config.paths import feature_path

scenarios(str(feature_path("admin_user_lifecycle")))


# ─────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────

@given(parsers.re(r'I am logged in as "(?P<role>[^"]*)"'))
def logged_in_as(login_page, dashboard_page, credentials, base_url, role) -> None:
    username, password = credentials(role)
    login_page.open(base_url)
    login_page.login_as(username, password)
    assert dashboard_page.is_loaded(), "Dashboard did not load after login"


@given("I am on the Users list page")
def on_users_list(admin_users_page, base_url) -> None:
    admin_users_page.open(base_url)
    assert admin_users_page.is_loaded(), "Admin Users list did not load"


# ─────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────

@when("I click the Add button on the Users list")
def click_add_button(admin_users_page) -> None:
    admin_users_page.click_add()


@when(parsers.re(r'I select the user role "(?P<role>[^"]*)"'))
def select_user_role(admin_add_user_page, role) -> None:
    assert admin_add_user_page.is_loaded(), "Add User form did not load"
    admin_add_user_page.select_user_role(role)


@when(parsers.re(r'I enter the employee name hint "(?P<hint>[^"]*)" and select the first suggestion'))
def enter_employee_name_and_select(admin_add_user_page, hint) -> None:
    admin_add_user_page.select_first_employee_suggestion(hint)


@when(parsers.re(r'I select the status "(?P<status>[^"]*)"'))
def select_status(admin_add_user_page, status) -> None:
    admin_add_user_page.select_status(status)


@when("I enter a run-unique username in the Username field")
def enter_unique_username(admin_add_user_page, unique_username) -> None:
    admin_add_user_page.enter_username(unique_username)


@when(parsers.re(r'I enter the password "(?P<password>[^"]*)" and confirm password "(?P<confirm>[^"]*)"'))
def enter_passwords(admin_add_user_page, password, confirm) -> None:
    admin_add_user_page.enter_password(password)
    admin_add_user_page.enter_confirm_password(confirm)


@when("I click the Save button")
def click_save(admin_add_user_page) -> None:
    admin_add_user_page.click_save()


@when("I search the Users list for the run-unique username")
def search_for_unique_username(admin_users_page, unique_username) -> None:
    assert admin_users_page.is_loaded(), "Admin Users list did not load"
    admin_users_page.search_by_username(unique_username)


@when(parsers.re(r'I search the Users list for username "(?P<username>[^"]*)"'))
def search_for_literal_username(admin_users_page, username) -> None:
    admin_users_page.search_by_username(username)


@when("I click the delete icon on the single result row")
def click_delete_on_single_row(admin_users_page) -> None:
    assert admin_users_page.get_record_count() == 1, "Expected exactly one row before deleting"
    admin_users_page.click_row_delete()


@when("I confirm the deletion")
def confirm_deletion(admin_users_page) -> None:
    admin_users_page.confirm_delete()


@when("I cancel the deletion")
def cancel_deletion(admin_users_page) -> None:
    admin_users_page.cancel_delete()


# ─────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────

@then("I should see a success toast")
def assert_success_toast(admin_add_user_page) -> None:
    toast = admin_add_user_page.get_toast_text()
    assert toast.strip(), f"Expected a success toast, got {toast!r}"


@then(parsers.re(r'the results summary should read "(?P<expected>[^"]*)"'))
def assert_results_summary(admin_users_page, expected) -> None:
    if expected == "No Records Found":
        assert admin_users_page.has_no_records(), "Expected the no-records indicator"
    else:
        actual = admin_users_page.get_records_summary()
        assert expected in actual, f"Expected {expected!r} in summary {actual!r}"


@then("the single result row should contain the run-unique username")
def assert_row_contains_username(admin_users_page, unique_username) -> None:
    row_text = admin_users_page.get_row_username()
    assert unique_username in row_text, f"Expected {unique_username!r} in row {row_text!r}"


@then("the delete confirmation dialog should be displayed")
def assert_delete_dialog(admin_users_page) -> None:
    assert admin_users_page.is_delete_dialog_open(), "Expected the delete confirmation dialog"
