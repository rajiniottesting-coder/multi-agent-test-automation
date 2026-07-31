"""Step definitions for features/admin_user_lifecycle.feature.

Binds the admin user create -> search -> delete lifecycle to page-object
methods on AdminUsersPage and AdminAddUserPage. Selectors live only in the
page objects; these steps call business-verb methods and assert.
"""
import datetime

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
    """A run-unique username owned by this test on the shared demo."""
    stamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    return f"qa_{unique_username}_{stamp}"


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
def on_users_list(admin_users_page, menu_page) -> None:
    menu_page.go_to("Admin")
    admin_users_page.wait_for_list()


# ─────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────

@when("I click the Add button on the Users list")
def click_add(admin_users_page) -> None:
    admin_users_page.click_add()


@when(parsers.parse('I select "{role}" from the User Role dropdown'))
def select_user_role(admin_add_user_page, role) -> None:
    admin_add_user_page.select_user_role(role)


@when(parsers.parse('I select an employee whose name starts with "{prefix}"'))
def select_employee(admin_add_user_page, prefix) -> None:
    admin_add_user_page.enter_employee_name(prefix)


@when(parsers.parse('I select "{status}" from the Status dropdown'))
def select_status(admin_add_user_page, status) -> None:
    admin_add_user_page.select_status(status)


@when("I enter a run-unique username for user creation")
def enter_unique_username(admin_add_user_page, created_username) -> None:
    admin_add_user_page.enter_username(created_username)


@when(parsers.parse('I enter the password "{password}" and confirm password "{confirm}"'))
def enter_passwords(admin_add_user_page, password, confirm) -> None:
    admin_add_user_page.enter_password(password)
    admin_add_user_page.enter_confirm_password(confirm)


@when("I click Save on the Add User form")
def click_save(admin_add_user_page) -> None:
    admin_add_user_page.click_save()


@when("I search the Users list for the created username")
def search_created_username(admin_users_page, created_username) -> None:
    admin_users_page.search_by_username(created_username)


@when(parsers.parse('I search the Users list for username "{username}"'))
def search_literal_username(admin_users_page, username) -> None:
    admin_users_page.search_by_username(username)


@when("I click the delete icon on the single result row")
def click_delete_icon(admin_users_page) -> None:
    assert admin_users_page.get_row_count() == 1, \
        "Expected exactly one result row before deleting"
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
def assert_success_toast(admin_users_page) -> None:
    toast = admin_users_page.get_toast_text()
    assert toast, f"Expected a success toast, got {toast!r}"


@then(parsers.parse('the results summary should contain "{fragment}"'))
def assert_summary_contains(admin_users_page, fragment) -> None:
    admin_users_page.wait_for_record_summary(fragment)
    summary = admin_users_page.get_record_summary()
    assert fragment in summary, f"Expected {fragment!r} in summary {summary!r}"


@then("the result row username should equal the created username")
def assert_row_username(admin_users_page, created_username) -> None:
    actual = admin_users_page.get_row_username()
    assert actual == created_username, \
        f"Expected row username {created_username!r}, got {actual!r}"


@then("the delete confirmation dialog should appear")
def assert_delete_dialog(admin_users_page) -> None:
    assert admin_users_page.is_delete_dialog_displayed(), \
        "Expected the delete confirmation dialog to appear"
    assert admin_users_page.has_confirm_delete_button(), \
        "Expected a 'Yes, Delete' button in the confirmation dialog"


@then(parsers.parse('the results summary should read "{expected}"'))
def assert_summary_reads(admin_users_page, expected) -> None:
    admin_users_page.wait_for_record_summary(expected)
    summary = admin_users_page.get_record_summary()
    assert expected in summary, f"Expected {expected!r} in summary {summary!r}"


@then("no success toast should be shown")
def assert_no_toast(admin_users_page) -> None:
    assert not admin_users_page.has_toast(), \
        "Expected no success toast after cancelling the deletion"
