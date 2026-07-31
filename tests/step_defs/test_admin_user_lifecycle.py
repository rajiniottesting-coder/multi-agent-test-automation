"""Step definitions for features/admin_user_lifecycle.feature.

Binds the admin user create/find/delete lifecycle scenarios to the admin
page objects, following the login step-def style:

- Every step the paired feature uses is declared here (module-scoped).
- Step defs call page-object methods only; no selectors leak in.
- Real logins go through a ROLE via the `credentials` fixture.
- Created usernames are run-unique, derived from `unique_username`, so
  assertions read the application's true rendered state on the shared demo.
- Between the two delete attempts in the cancel scenario, the search is
  re-run before asserting, so no stale UI state is mistaken for a fresh one.
"""
import pytest
from pytest_bdd import given, when, then, parsers, scenarios

from config.paths import feature_path

scenarios(str(feature_path("admin_user_lifecycle")))


# ─────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────

@pytest.fixture
def created_username(unique_username) -> str:
    """A run-unique username owned by this test, safe on the shared demo."""
    return f"qa_lifecycle_{unique_username}"


# ─────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────

@given(parsers.re(r'I am logged in as "(?P<role>[^"]*)"'))
def login_as_role(login_page, dashboard_page, credentials, role, base_url) -> None:
    username, password = credentials(role)
    login_page.open(base_url)
    login_page.login_as(username, password)
    assert dashboard_page.is_loaded(), "Dashboard did not load after login"


@given("I am on the Users list page")
def open_users_list(admin_users_page, base_url) -> None:
    admin_users_page.open(base_url)


@given("a run-unique system user has been created")
def create_run_unique_user(admin_users_page, admin_add_user_page, created_username) -> None:
    admin_users_page.click_add()
    assert admin_add_user_page.is_loaded(), "Add User form did not load"
    admin_add_user_page.select_user_role("ESS")
    admin_add_user_page.enter_employee_name("a")
    admin_add_user_page.select_status("Enabled")
    admin_add_user_page.enter_username(created_username)
    admin_add_user_page.enter_password("Passw0rd1")
    admin_add_user_page.enter_confirm_password("Passw0rd1")
    admin_add_user_page.click_save()
    assert admin_users_page.has_toast(), "Expected a success toast after creating the user"


# ─────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────

@when("I click the Add button")
def click_add(admin_users_page) -> None:
    admin_users_page.click_add()


@when(parsers.re(r'I select the user role "(?P<role>[^"]*)"'))
def select_user_role(admin_add_user_page, role) -> None:
    admin_add_user_page.select_user_role(role)


@when("I select an employee from the autocomplete")
def select_employee(admin_add_user_page) -> None:
    admin_add_user_page.enter_employee_name("a")


@when(parsers.re(r'I select the status "(?P<status>[^"]*)"'))
def select_status(admin_add_user_page, status) -> None:
    admin_add_user_page.select_status(status)


@when("I enter a run-unique username")
def enter_run_unique_username(admin_add_user_page, created_username) -> None:
    admin_add_user_page.enter_username(created_username)


@when(parsers.re(r'I enter the password "(?P<password>[^"]*)"'))
def enter_password(admin_add_user_page, password) -> None:
    admin_add_user_page.enter_password(password)


@when(parsers.re(r'I enter the confirm password "(?P<password>[^"]*)"'))
def enter_confirm_password(admin_add_user_page, password) -> None:
    admin_add_user_page.enter_confirm_password(password)


@when("I click the Save button")
def click_save(admin_add_user_page) -> None:
    admin_add_user_page.click_save()


@when("I search for the created username")
def search_created_username(admin_users_page, created_username) -> None:
    admin_users_page.search_by_username(created_username)


@when(parsers.re(r'I search the users list for username "(?P<username>[^"]*)"'))
def search_literal_username(admin_users_page, username) -> None:
    admin_users_page.search_by_username(username)


@when("I click the delete icon on the matching row")
def click_delete_icon(admin_users_page) -> None:
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

@then("no field error should be shown on the add user form")
def assert_no_field_error(admin_add_user_page) -> None:
    assert not admin_add_user_page.has_field_error(), "Expected no field error on the add user form"


@then("I should see a success toast on the users list")
def assert_success_toast(admin_users_page) -> None:
    assert admin_users_page.has_toast(), "Expected a success toast on the users list"


@then(parsers.re(r'the results summary should read "(?P<expected>[^"]*)"'))
def assert_results_summary(admin_users_page, expected) -> None:
    actual = admin_users_page.get_records_summary()
    assert expected in actual, f"Expected summary {expected!r} in {actual!r}"


@then("the single result row should contain the created username")
def assert_row_contains_username(admin_users_page, created_username) -> None:
    row_username = admin_users_page.get_row_username()
    assert created_username in row_username, (
        f"Expected {created_username!r} in row username {row_username!r}"
    )


@then("the delete confirmation dialog should be displayed")
def assert_delete_dialog(admin_users_page) -> None:
    assert admin_users_page.is_delete_dialog_open(), "Expected the delete confirmation dialog"


@then("no success toast should be shown on the users list")
def assert_no_success_toast(admin_users_page) -> None:
    assert not admin_users_page.has_toast(), "Expected no success toast after cancelling"
