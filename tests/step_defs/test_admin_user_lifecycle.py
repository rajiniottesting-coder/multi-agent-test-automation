"""Step definitions for features/admin_user_lifecycle.feature.

Binds the admin user lifecycle scenarios (create → find → delete, cancel-delete
edge case, and negative empty-search) to the Admin page objects.

Conventions followed:
- Log in by ROLE via the `credentials` fixture; credentials never appear here.
- Interact with the UI exclusively through page-object METHODS — no selectors.
- Created records use a run-unique username derived from `unique_username`, so
  the shared demo stays deterministic and cleanup is owned by this test.
"""
import pytest
from pytest_bdd import given, when, then, parsers, scenarios

from config.paths import feature_path

scenarios(str(feature_path("admin_user_lifecycle")))


# ─────────────────────────────────────────────────────────────
# Shared state
# ─────────────────────────────────────────────────────────────

class _Context:
    """Carries the run-unique username between steps in a scenario."""

    def __init__(self) -> None:
        self.username: str = ""


@pytest.fixture
def ctx() -> _Context:
    return _Context()


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


@given(parsers.re(r'a run-unique system user has been created with role "(?P<role>[^"]*)" and status "(?P<status>[^"]*)" and password "(?P<password>[^"]*)"'))
def create_run_unique_user(
    admin_users_page,
    admin_add_user_page,
    base_url,
    unique_username,
    ctx,
    role,
    status,
    password,
) -> None:
    ctx.username = unique_username
    admin_users_page.open(base_url)
    admin_users_page.click_add()
    admin_add_user_page.select_user_role(role)
    admin_add_user_page.enter_employee_name("a")
    admin_add_user_page.select_status(status)
    admin_add_user_page.enter_username(ctx.username)
    admin_add_user_page.enter_password(password)
    admin_add_user_page.enter_confirm_password(password)
    admin_add_user_page.click_save()
    toast = admin_add_user_page.get_toast_text()
    assert toast, "Expected a success toast after saving the user"


# ─────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────

@when("I click the Add button on the Users list")
def click_add_button(admin_users_page) -> None:
    admin_users_page.click_add()


@when(parsers.re(r'I select "(?P<role>[^"]*)" as the User Role'))
def select_user_role(admin_add_user_page, role) -> None:
    admin_add_user_page.select_user_role(role)


@when(parsers.re(r'I select an employee by typing "(?P<query>[^"]*)" in the Employee Name field'))
def select_employee(admin_add_user_page, query) -> None:
    admin_add_user_page.enter_employee_name(query)


@when(parsers.re(r'I select "(?P<status>[^"]*)" as the Status'))
def select_status(admin_add_user_page, status) -> None:
    admin_add_user_page.select_status(status)


@when("I enter a run-unique username in the Add User form")
def enter_unique_username(admin_add_user_page, unique_username, ctx) -> None:
    ctx.username = unique_username
    admin_add_user_page.enter_username(ctx.username)


@when(parsers.re(r'I enter the password "(?P<password>[^"]*)" and confirm password "(?P<confirm>[^"]*)"'))
def enter_passwords(admin_add_user_page, password, confirm) -> None:
    admin_add_user_page.enter_password(password)
    admin_add_user_page.enter_confirm_password(confirm)


@when("I click the Save button")
def click_save(admin_add_user_page) -> None:
    admin_add_user_page.click_save()


@when("I search the Users list for my created username")
def search_created_username(admin_users_page, ctx) -> None:
    admin_users_page.search_by_username(ctx.username)


@when(parsers.re(r'I search the Users list for username "(?P<username>[^"]*)"'))
def search_literal_username(admin_users_page, username) -> None:
    admin_users_page.search_by_username(username)


@when("I click the delete icon on the single result row")
def click_delete_icon(admin_users_page) -> None:
    assert admin_users_page.row_count() == 1, (
        "Expected exactly one row before deleting; refusing to click delete "
        "on an ambiguous list on the shared demo"
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


@then(parsers.re(r'the results summary should read "(?P<summary>[^"]*)"'))
def assert_results_summary(admin_users_page, summary) -> None:
    admin_users_page.wait_for_records_found(summary)
    actual = admin_users_page.get_records_summary()
    assert summary in actual, f"Expected {summary!r} in results summary, got {actual!r}"


@then("the single result row should show my created username")
def assert_row_username(admin_users_page, ctx) -> None:
    assert admin_users_page.row_count() == 1, "Expected exactly one result row"
    row_username = admin_users_page.get_row_username()
    assert ctx.username in row_username, (
        f"Expected created username {ctx.username!r} in row {row_username!r}"
    )


@then("the delete confirmation dialog should be displayed")
def assert_delete_dialog(admin_users_page) -> None:
    assert admin_users_page.is_delete_dialog_open(), (
        "Expected the delete confirmation dialog to be displayed"
    )
