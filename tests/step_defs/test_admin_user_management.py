"""Step definitions for features/admin_user_management.feature.

Binds Gherkin steps to AdminUsersPage / AdminAddUserPage page-object methods.
Real logins go through the `credentials` fixture (login by ROLE). Created
records use a run-unique username so the shared demo stays deterministic.
"""
import pytest
from pytest_bdd import given, when, then, parsers, scenarios

from config.paths import feature_path
from pages.admin_users_page import AdminUsersPage
from pages.admin_add_user_page import AdminAddUserPage

scenarios(str(feature_path("admin_user_management")))


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
    """Run-unique username shared across steps within a scenario."""
    return f"qa_{unique_username}"


# ─────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────

@given(parsers.re(r'I am logged in as "(?P<role>[^"]*)"'))
def logged_in_as(login_page, dashboard_page, credentials, base_url, role) -> None:
    username, password = credentials(role)
    login_page.open(base_url)
    login_page.login_as(username, password)
    assert dashboard_page.is_loaded(), "Dashboard did not load after login"


@given("I am on the Admin Users list")
def on_admin_users_list(admin_users_page, base_url) -> None:
    admin_users_page.open(base_url)


# ─────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────

@when("I click the Add button on the Users list")
def click_add_button(admin_users_page) -> None:
    admin_users_page.click_add()


@when(parsers.re(r'I select the user role "(?P<role>[^"]*)"'))
def select_user_role(admin_add_user_page, role) -> None:
    admin_add_user_page.select_user_role(role)


@when(parsers.re(r'I enter an employee name starting with "(?P<letter>[^"]*)"'))
def enter_employee_name(admin_add_user_page, letter) -> None:
    admin_add_user_page.enter_employee_name(letter)


@when(parsers.re(r'I select the status "(?P<status>[^"]*)"'))
def select_status(admin_add_user_page, status) -> None:
    admin_add_user_page.select_status(status)


@when("I enter a run-unique username")
def enter_run_unique_username(admin_add_user_page, created_username) -> None:
    admin_add_user_page.enter_username(created_username)


@when(parsers.re(r'I enter the password "(?P<password>[^"]*)" and confirm password "(?P<confirm>[^"]*)"'))
def enter_passwords(admin_add_user_page, password, confirm) -> None:
    admin_add_user_page.enter_password(password)
    admin_add_user_page.enter_confirm_password(confirm)


@when("I save the user")
def save_user(admin_add_user_page) -> None:
    admin_add_user_page.click_save()


@when("I search the Users list for the created username")
def search_created_username(admin_users_page, created_username) -> None:
    admin_users_page.search_by_username(created_username)


@when(parsers.re(r'I search the Users list for username "(?P<username>[^"]*)"'))
def search_literal_username(admin_users_page, username) -> None:
    admin_users_page.search_by_username(username)


@when("I delete the created user and confirm the deletion")
def delete_and_confirm(admin_users_page) -> None:
    admin_users_page.delete_first_row()
    assert admin_users_page.is_confirm_dialog_visible(), "Confirm dialog did not open"
    admin_users_page.confirm_delete()


@when("I delete the created user and cancel the deletion")
def delete_and_cancel(admin_users_page) -> None:
    admin_users_page.delete_first_row()
    assert admin_users_page.is_confirm_dialog_visible(), "Confirm dialog did not open"
    admin_users_page.cancel_delete()


# ─────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────

@then("I should see a success toast")
def assert_success_toast(admin_users_page) -> None:
    toast = admin_users_page.get_toast_text()
    assert toast, f"Expected a success toast, got {toast!r}"


@then("I should not see a success toast")
def assert_no_success_toast(admin_users_page) -> None:
    assert not admin_users_page.get_toast_text(), "Unexpected success toast after cancel"


@then(parsers.re(r'the results summary should read "(?P<summary>[^"]*)"'))
def assert_results_summary(admin_users_page, summary) -> None:
    if summary == "No Records Found":
        assert admin_users_page.has_no_records(), "Expected the no-records indicator"
    else:
        actual = admin_users_page.get_records_summary()
        assert summary in actual, f"Expected {summary!r} in {actual!r}"


@then("the single result row should show the created username")
def assert_row_shows_username(admin_users_page, created_username) -> None:
    assert admin_users_page.get_record_count() == 1, "Expected exactly one result row"
    row_text = admin_users_page.get_first_row_text()
    assert created_username in row_text, f"Expected {created_username!r} in {row_text!r}"
