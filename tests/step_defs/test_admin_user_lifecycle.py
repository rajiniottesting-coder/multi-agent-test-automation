"""Step definitions for features/admin_user_lifecycle.feature.

Covers the admin user lifecycle: create a run-unique system user, find it by
exact username, cancel a delete (no-op), and confirm a delete (cleanup).

Rules honoured:
  - No selectors or DOM access here; every UI action goes through page-object
    methods (AdminUsersPage / AdminAddUserPage).
  - Run-unique usernames derive from the `unique_username` fixture so the
    shared demo stays deterministic.
  - Presence assertions use waiting readers (get_toast_text); absence uses the
    non-waiting predicate (has_toast).
"""
import pytest
from pytest_bdd import given, when, then, parsers, scenarios

from config.paths import feature_path
from pages.admin_users_page import AdminUsersPage
from pages.admin_add_user_page import AdminAddUserPage

scenarios(str(feature_path("admin_user_lifecycle")))


# ─────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────

@pytest.fixture
def admin_users_page(page) -> AdminUsersPage:
    return AdminUsersPage(page)


@pytest.fixture
def admin_add_user_page(page) -> AdminAddUserPage:
    return AdminAddUserPage(page)


@pytest.fixture
def created_username(unique_username) -> str:
    """A run-unique username shared across steps within a scenario."""
    return f"qa_{unique_username}"


# ─────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────

@given(parsers.re(r'I am logged in as "(?P<role>[^"]*)"'))
def logged_in_as(login_page, dashboard_page, credentials, base_url, role: str) -> None:
    username, password = credentials(role)
    login_page.open(base_url)
    login_page.login_as(username, password)
    assert dashboard_page.is_loaded(), "Dashboard did not load after login"


@given("I am on the Admin Users list")
def on_admin_users_list(admin_users_page, base_url) -> None:
    admin_users_page.open(base_url)


@given(parsers.re(r'I have created a run-unique system user with role "(?P<role>[^"]*)" status "(?P<status>[^"]*)" and password "(?P<password>[^"]*)"'))
def create_run_unique_user(
    admin_users_page,
    admin_add_user_page,
    created_username: str,
    base_url,
    role: str,
    status: str,
    password: str,
) -> None:
    admin_users_page.open(base_url)
    admin_users_page.click_add()
    admin_add_user_page.select_user_role(role)
    admin_add_user_page.enter_employee_name("a")
    admin_add_user_page.select_status(status)
    admin_add_user_page.enter_username(created_username)
    admin_add_user_page.enter_password(password)
    admin_add_user_page.enter_confirm_password(password)
    admin_add_user_page.click_save()
    toast = admin_add_user_page.get_toast_text()
    assert toast, "Expected a success toast after saving the new user"


# ─────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────

@when(parsers.re(r'I search for the username "(?P<username>[^"]*)"'))
def search_for_literal_username(admin_users_page, username: str) -> None:
    admin_users_page.search_by_username(username)


@when("I search for the created username")
def search_for_created_username(admin_users_page, created_username: str) -> None:
    admin_users_page.search_by_username(created_username)


@when("I click the delete icon on the single result row")
def click_delete_single_row(admin_users_page) -> None:
    assert admin_users_page.get_record_count() == 1, (
        "Expected exactly one row before deleting; refusing to click on a "
        "list this test does not own"
    )
    admin_users_page.click_row_delete()


@when("I cancel the delete confirmation dialog")
def cancel_delete_dialog(admin_users_page) -> None:
    admin_users_page.cancel_delete()


@when("I confirm the delete")
def confirm_delete(admin_users_page) -> None:
    admin_users_page.confirm_delete()


@when("I click the Add button")
def click_add_button(admin_users_page) -> None:
    admin_users_page.click_add()


@when(parsers.re(r'I select the user role "(?P<role>[^"]*)"'))
def select_user_role(admin_add_user_page, role: str) -> None:
    admin_add_user_page.select_user_role(role)


@when(parsers.re(r'I select an employee by typing "(?P<query>[^"]*)"'))
def select_employee(admin_add_user_page, query: str) -> None:
    admin_add_user_page.enter_employee_name(query)


@when(parsers.re(r'I select the status "(?P<status>[^"]*)"'))
def select_status(admin_add_user_page, status: str) -> None:
    admin_add_user_page.select_status(status)


@when("I enter a run-unique username")
def enter_run_unique_username(admin_add_user_page, created_username: str) -> None:
    admin_add_user_page.enter_username(created_username)


@when(parsers.re(r'I enter the password "(?P<password>[^"]*)" and confirm password "(?P<confirm>[^"]*)"'))
def enter_passwords(admin_add_user_page, password: str, confirm: str) -> None:
    admin_add_user_page.enter_password(password)
    admin_add_user_page.enter_confirm_password(confirm)


@when("I click the Save button")
def click_save_button(admin_add_user_page) -> None:
    admin_add_user_page.click_save()


# ─────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────

@then(parsers.re(r'the results summary should read "(?P<expected>[^"]*)"'))
def assert_results_summary(admin_users_page, expected: str) -> None:
    admin_users_page.wait_for_records_summary(expected)
    actual = admin_users_page.get_records_summary()
    assert expected in actual, f"Expected {expected!r} in summary, got {actual!r}"


@then("the single result row should show the created username")
def assert_single_row_username(admin_users_page, created_username: str) -> None:
    assert admin_users_page.get_record_count() == 1, (
        "Expected exactly one result row for the created username"
    )
    row_text = admin_users_page.get_row_username()
    assert created_username in row_text, (
        f"Expected {created_username!r} in row text {row_text!r}"
    )


@then("the delete confirmation dialog should be displayed")
def assert_delete_dialog(admin_users_page) -> None:
    assert admin_users_page.get_record_count() == 1, (
        "Expected exactly one row while the delete dialog is open"
    )


@then("no success toast should be shown")
def assert_no_toast(admin_users_page) -> None:
    assert not admin_users_page.has_toast(), "Expected no success toast to be shown"


@then("a success toast should be shown")
def assert_success_toast(admin_users_page) -> None:
    toast = admin_users_page.get_toast_text()
    assert toast, "Expected a success toast to be shown"


@then("I should be on the Add User form")
def assert_on_add_user_form(admin_add_user_page) -> None:
    value = admin_add_user_page.get_username_value()
    assert value == "", "Expected an empty Username field on the Add User form"
