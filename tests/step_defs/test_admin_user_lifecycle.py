"""Step definitions for features/admin_user_lifecycle.feature.

Binds the admin user lifecycle scenarios (create / search / delete) to the
Admin page objects. Real logins go through the ROLE-based credentials fixture;
usernames created by these tests are run-unique so they never collide on the
shared demo instance.

The run-unique username created during a scenario is stashed on a per-scenario
`bdd_context` dict so later "search for the created username" steps can retrieve
exactly what earlier steps created.
"""
import pytest
from pytest_bdd import given, when, then, parsers, scenarios

from config.paths import feature_path

scenarios(str(feature_path("admin_user_lifecycle")))


# ─────────────────────────────────────────────────────────────
# Scenario-scoped shared state
# ─────────────────────────────────────────────────────────────

@pytest.fixture
def bdd_context() -> dict:
    """Per-scenario scratch space for values shared between steps."""
    return {}


def _created_username(context: dict, unique_username: str) -> str:
    """Return (creating on first access) the run-unique username for this test."""
    if "created_username" not in context:
        context["created_username"] = f"qa_{unique_username}"
    return context["created_username"]


# ─────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────

@given(parsers.re(r'I am logged in as "(?P<role>[^"]*)"'))
def logged_in_as(login_page, dashboard_page, credentials, base_url, role) -> None:
    username, password = credentials(role)
    login_page.open(base_url)
    login_page.login_as(username, password)
    assert dashboard_page.is_loaded(), "Dashboard did not load after admin login"


@given("I am on the Users list page")
def on_users_list(admin_users_page, base_url) -> None:
    admin_users_page.open(base_url)
    assert admin_users_page.is_loaded(), "Admin Users list did not load"


@given(parsers.re(r'a run-unique system user with role "(?P<role>[^"]*)" and status "(?P<status>[^"]*)" and password "(?P<password>[^"]*)" has been created'))
def create_run_unique_user(
    admin_users_page,
    admin_add_user_page,
    unique_username,
    bdd_context,
    base_url,
    role,
    status,
    password,
) -> None:
    admin_users_page.open(base_url)
    assert admin_users_page.is_loaded(), "Admin Users list did not load"
    admin_users_page.click_add()
    assert admin_add_user_page.is_loaded(), "Add User form did not load"

    admin_add_user_page.select_user_role(role)
    admin_add_user_page.enter_employee_name_first_suggestion("a")
    admin_add_user_page.select_status(status)

    username = _created_username(bdd_context, unique_username)
    admin_add_user_page.enter_username(username)
    admin_add_user_page.enter_password(password)
    admin_add_user_page.enter_confirm_password(password)
    admin_add_user_page.click_save()

    toast = admin_add_user_page.get_toast_text()
    assert toast, f"Expected a success toast after creating the user, got {toast!r}"


# ─────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────

@when("I click the Add button on the Users list")
def click_add_button(admin_users_page) -> None:
    admin_users_page.click_add()


@when(parsers.re(r'I select the user role "(?P<role>[^"]*)"'))
def select_user_role(admin_add_user_page, role) -> None:
    admin_add_user_page.select_user_role(role)


@when('I enter the letter "a" in the Employee Name autocomplete and pick the first suggestion')
def enter_employee_name_autocomplete(admin_add_user_page) -> None:
    admin_add_user_page.enter_employee_name_first_suggestion("a")


@when(parsers.re(r'I select the status "(?P<status>[^"]*)"'))
def select_status(admin_add_user_page, status) -> None:
    admin_add_user_page.select_status(status)


@when("I enter a run-unique username in the Add User form")
def enter_run_unique_username(admin_add_user_page, bdd_context, unique_username) -> None:
    username = _created_username(bdd_context, unique_username)
    admin_add_user_page.enter_username(username)


@when(parsers.re(r'I enter the password "(?P<password>[^"]*)" and confirm password "(?P<confirm>[^"]*)"'))
def enter_passwords(admin_add_user_page, password, confirm) -> None:
    admin_add_user_page.enter_password(password)
    admin_add_user_page.enter_confirm_password(confirm)


@when("I save the new user")
def save_new_user(admin_add_user_page) -> None:
    admin_add_user_page.click_save()


@when("I search the Users list for the created username")
def search_created_username(admin_users_page, bdd_context, unique_username) -> None:
    username = _created_username(bdd_context, unique_username)
    admin_users_page.search_by_username(username)


@when(parsers.re(r'I search the Users list for username "(?P<username>[^"]*)"'))
def search_literal_username(admin_users_page, username) -> None:
    admin_users_page.search_by_username(username)


@when("I click the delete icon on the single result row")
def click_delete_icon(admin_users_page) -> None:
    assert admin_users_page.get_record_count() == 1, (
        "Refusing to delete: expected exactly one result row before clicking delete"
    )
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
    assert toast, f"Expected a success toast, got {toast!r}"


@then(parsers.re(r'the results summary should read "(?P<expected>[^"]*)"'))
def assert_results_summary(admin_users_page, expected) -> None:
    actual = admin_users_page.get_records_found_text()
    assert expected in actual, f"Expected results summary {expected!r} in {actual!r}"


@then("the single result row should contain the created username")
def assert_row_contains_username(admin_users_page, bdd_context, unique_username) -> None:
    username = _created_username(bdd_context, unique_username)
    row_text = admin_users_page.get_row_username()
    assert username in row_text, f"Expected {username!r} in row text {row_text!r}"


@then("a delete confirmation dialog should be displayed")
def assert_delete_dialog(admin_users_page) -> None:
    assert admin_users_page.is_delete_dialog_open(), (
        "Expected the delete confirmation dialog to be displayed"
    )
