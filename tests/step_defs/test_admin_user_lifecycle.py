"""Step definitions for features/admin_user_lifecycle.feature.

Binds the admin user lifecycle steps to AdminUsersPage and AdminAddUserPage.

Rules honoured here:
- Every step interacts with the UI only through page-object methods.
- Logins go through a ROLE via the `credentials` fixture; no literal secrets.
- Created records use a run-unique username derived from `unique_username`,
  because the demo is a shared application.
- Absence assertions use non-waiting predicates (has_no_records, has_toast).
"""
import pytest
from pytest_bdd import given, when, then, parsers, scenarios

from config.paths import feature_path

scenarios(str(feature_path("admin_user_lifecycle")))


# ─────────────────────────────────────────────────────────────
# Shared per-scenario state
# ─────────────────────────────────────────────────────────────

@pytest.fixture
def created_username(unique_username) -> str:
    """A run-unique username the test owns for the duration of the scenario."""
    return f"qa_lifecycle_{unique_username}"


def _create_user(admin_add_user_page, username: str, role: str,
                 status: str, password: str) -> None:
    """Fill and submit the Add User form for a run-unique account."""
    admin_add_user_page.select_user_role(role)
    admin_add_user_page.enter_employee_name("a")
    admin_add_user_page.select_status(status)
    admin_add_user_page.enter_username(username)
    admin_add_user_page.enter_password(password)
    admin_add_user_page.enter_confirm_password(password)
    admin_add_user_page.click_save()


# ─────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────

@given(parsers.re(r'I am logged in as "(?P<role>[^"]*)"'))
def logged_in_as(login_page, dashboard_page, credentials, base_url, role):
    username, password = credentials(role)
    login_page.open(base_url)
    login_page.login_as(username, password)
    assert dashboard_page.is_loaded(), "Dashboard did not load after login"


@given("I am on the Users list page")
def on_users_list(admin_users_page, base_url):
    admin_users_page.open(base_url)


@given(parsers.re(r'I have created a run-unique system user with role "(?P<role>[^"]*)" and status "(?P<status>[^"]*)" and password "(?P<password>[^"]*)"'))
def create_run_unique_user(admin_users_page, admin_add_user_page,
                           created_username, base_url, role, status, password):
    admin_users_page.open(base_url)
    admin_users_page.click_add()
    _create_user(admin_add_user_page, created_username, role, status, password)
    assert admin_add_user_page.has_toast(), "Expected a success toast after saving the user"


# ─────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────

@when("I click the Add button on the Users list")
def click_add(admin_users_page):
    admin_users_page.click_add()


@when(parsers.re(r'I select the user role "(?P<role>[^"]*)"'))
def select_user_role(admin_add_user_page, role):
    admin_add_user_page.select_user_role(role)


@when(parsers.re(r'I enter the employee name starting with "(?P<letter>[^"]*)" and pick the first suggestion'))
def enter_employee_name(admin_add_user_page, letter):
    admin_add_user_page.enter_employee_name(letter)


@when(parsers.re(r'I select the status "(?P<status>[^"]*)"'))
def select_status(admin_add_user_page, status):
    admin_add_user_page.select_status(status)


@when("I enter a run-unique username")
def enter_run_unique_username(admin_add_user_page, created_username):
    admin_add_user_page.enter_username(created_username)


@when(parsers.re(r'I enter the password "(?P<password>[^"]*)" and confirm password "(?P<confirm>[^"]*)"'))
def enter_passwords(admin_add_user_page, password, confirm):
    admin_add_user_page.enter_password(password)
    admin_add_user_page.enter_confirm_password(confirm)


@when("I click the Save button")
def click_save(admin_add_user_page):
    admin_add_user_page.click_save()


@when("I search the Users list for the created username")
def search_created_username(admin_users_page, created_username):
    admin_users_page.search_by_username(created_username)


@when(parsers.re(r'I search the Users list for username "(?P<username>[^"]*)"'))
def search_literal_username(admin_users_page, username):
    admin_users_page.search_by_username(username)


@when("I click the delete icon on the matching row")
def click_delete_icon(admin_users_page):
    assert admin_users_page.get_record_count() == 1, \
        "Expected exactly one owned row before deleting"
    admin_users_page.click_row_delete()


@when("I confirm the deletion")
def confirm_deletion(admin_users_page):
    admin_users_page.confirm_delete()


@when("I cancel the deletion")
def cancel_deletion(admin_users_page):
    admin_users_page.cancel_delete()


# ─────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────

@then("I should see a success toast")
def assert_success_toast(admin_add_user_page):
    assert admin_add_user_page.has_toast(), "Expected a success toast to be shown"


@then("I should not see a success toast")
def assert_no_success_toast(admin_users_page):
    assert not admin_users_page.has_toast(), "Expected no success toast to be shown"


@then(parsers.re(r'the results summary should read "(?P<expected>[^"]*)"'))
def assert_results_summary(admin_users_page, expected):
    if expected == "No Records Found":
        assert admin_users_page.has_no_records(), \
            "Expected the 'No Records Found' indicator"
    else:
        actual = admin_users_page.get_records_summary()
        assert expected in actual, f"Expected {expected!r} in {actual!r}"


@then("the single row username should match the created username")
def assert_single_row_username(admin_users_page, created_username):
    assert admin_users_page.get_record_count() == 1, \
        "Expected exactly one matching row"
    row_username = admin_users_page.get_row_username()
    assert created_username in row_username, \
        f"Expected {created_username!r} in row username {row_username!r}"
