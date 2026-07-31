"""Step definitions for features/admin_user_lifecycle.feature.

Binds the admin user lifecycle scenarios (SCRUM-104/105/106) to page-object
methods. Every step interacts with the UI only through page-object verbs;
no selectors appear here. Run-unique usernames are derived from the
unique_username fixture so the shared demo stays deterministic.
"""
import pytest
from pytest_bdd import given, when, then, parsers, scenarios

from config.paths import feature_path

scenarios(str(feature_path("admin_user_lifecycle")))


# ─────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────

@pytest.fixture
def lifecycle_context(unique_username) -> dict:
    """Holds run-scoped data shared across steps (the run-unique username)."""
    return {
        "username": unique_username,
        "missing_username": f"zzz_nonexistent_{unique_username}",
    }


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
    assert admin_users_page.is_loaded(), "Admin Users list did not load"


@given(parsers.re(r'a run-unique system user has been created with role "(?P<role>[^"]*)" status "(?P<status>[^"]*)" and password "(?P<password>[^"]*)"'))
def create_run_unique_user(
    admin_users_page,
    admin_add_user_page,
    base_url,
    lifecycle_context,
    role,
    status,
    password,
) -> None:
    admin_users_page.open(base_url)
    admin_users_page.click_add()
    assert admin_add_user_page.is_loaded(), "Add User form did not load"
    admin_add_user_page.select_user_role(role)
    admin_add_user_page.enter_employee_name("a")
    admin_add_user_page.select_status(status)
    admin_add_user_page.enter_username(lifecycle_context["username"])
    admin_add_user_page.enter_password(password)
    admin_add_user_page.enter_confirm_password(password)
    assert not admin_add_user_page.has_field_error(), (
        f"Unexpected field errors before Save: {admin_add_user_page.get_all_field_errors()}"
    )
    admin_add_user_page.click_save()
    assert admin_add_user_page.get_toast_text(), "No success toast after creating user"
    admin_users_page.open(base_url)
    assert admin_users_page.is_loaded(), "Admin Users list did not reload after create"


# ─────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────

@when("I search the users list for a run-unique username that does not exist")
def search_for_missing_username(admin_users_page, lifecycle_context) -> None:
    admin_users_page.search_by_username(lifecycle_context["missing_username"])


@when("I search the users list for the created username")
def search_for_created_username(admin_users_page, lifecycle_context) -> None:
    admin_users_page.search_by_username(lifecycle_context["username"])


@when("I click the delete icon on the single result row")
def click_delete_icon(admin_users_page) -> None:
    assert admin_users_page.get_record_count() == 1, (
        "Expected exactly one result row before deleting"
    )
    admin_users_page.click_row_delete()


@when("I cancel the delete confirmation dialog")
def cancel_delete_dialog(admin_users_page) -> None:
    admin_users_page.cancel_delete()


@when("I confirm the delete")
def confirm_delete(admin_users_page) -> None:
    admin_users_page.confirm_delete()


@when("I click the Add button on the users list")
def click_add_button(admin_users_page) -> None:
    admin_users_page.click_add()


@when(parsers.re(r'I select the user role "(?P<role>[^"]*)"'))
def select_user_role(admin_add_user_page, role) -> None:
    admin_add_user_page.select_user_role(role)


@when(parsers.re(r'I select the first employee suggestion for the letter "(?P<letter>[^"]*)"'))
def select_employee_suggestion(admin_add_user_page, letter) -> None:
    admin_add_user_page.enter_employee_name(letter)


@when(parsers.re(r'I select the status "(?P<status>[^"]*)"'))
def select_status(admin_add_user_page, status) -> None:
    admin_add_user_page.select_status(status)


@when("I enter a run-unique username in the Add User form")
def enter_run_unique_username(admin_add_user_page, lifecycle_context) -> None:
    admin_add_user_page.enter_username(lifecycle_context["username"])


@when(parsers.re(r'I enter the password "(?P<password>[^"]*)" and confirm password "(?P<confirm>[^"]*)"'))
def enter_passwords(admin_add_user_page, password, confirm) -> None:
    admin_add_user_page.enter_password(password)
    admin_add_user_page.enter_confirm_password(confirm)


@when("I click the Save button")
def click_save_button(admin_add_user_page) -> None:
    admin_add_user_page.click_save()


# ─────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────

@then(parsers.re(r'the users search results should show "(?P<expected>[^"]*)"'))
def assert_records_summary(admin_users_page, expected) -> None:
    admin_users_page.wait_for_record_count(expected)
    actual = admin_users_page.get_records_summary()
    assert expected in actual, f"Expected {expected!r} in summary, got {actual!r}"


@then("the created username should be shown in the results row")
def assert_username_in_row(admin_users_page, lifecycle_context) -> None:
    row_text = admin_users_page.get_row_username()
    assert lifecycle_context["username"] in row_text, (
        f"Expected {lifecycle_context['username']!r} in row {row_text!r}"
    )


@then("the delete confirmation dialog should be displayed")
def assert_delete_dialog(admin_users_page) -> None:
    admin_users_page.wait_for_delete_dialog()
    assert admin_users_page.is_delete_dialog_open(), "Delete confirmation dialog not shown"


@then("no success toast should be shown")
def assert_no_toast(admin_users_page) -> None:
    assert not admin_users_page.has_toast(), "Unexpected success toast after cancel"


@then("a success toast should be shown")
def assert_success_toast(admin_users_page) -> None:
    assert admin_users_page.get_toast_text(), "Expected a success toast after delete"


@then("the Add User form should be displayed")
def assert_add_user_form(admin_add_user_page) -> None:
    assert admin_add_user_page.is_loaded(), "Add User form is not displayed"
