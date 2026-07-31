"""Step definitions for features/admin_user_lifecycle.feature.

Covers the full admin user lifecycle: create a run-unique system user, find it
by exact username, cancel a delete, then confirm the delete, plus a negative
search that yields the no-records indicator.

Conventions:
- Step defs call page-object METHODS only; no selectors, no page.* DOM calls.
- Real login goes through the ROLE via the `credentials` fixture.
- Run-unique usernames are derived from `unique_username` so the shared demo
  stays deterministic and this test only asserts on data it owns.
- The username created during a scenario is shared between steps via a
  module-local dict populated at `enter a run-unique username` time; there is
  no `created_username` fixture, so we keep the value on a plain function-scoped
  fixture defined in THIS file.
"""
import pytest
from pytest_bdd import given, when, then, parsers, scenarios

from config.paths import feature_path

scenarios(str(feature_path("admin_user_lifecycle")))


# ─────────────────────────────────────────────────────────────
# Local fixture — carries the created username across steps
# ─────────────────────────────────────────────────────────────

@pytest.fixture
def created_username() -> dict:
    """Mutable holder so create/search/delete steps share one username."""
    return {"value": ""}


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
    admin_users_page.wait_until_loaded()


# ─────────────────────────────────────────────────────────────
# When — create user
# ─────────────────────────────────────────────────────────────

@when("I click the Add button on the Users list")
def click_add(admin_users_page) -> None:
    admin_users_page.click_add()


@when(parsers.re(r'I select the User Role "(?P<role>[^"]*)"'))
def select_user_role(admin_add_user_page, role) -> None:
    admin_add_user_page.select_user_role(role)


@when(parsers.re(r'I enter the employee name prefix "(?P<prefix>[^"]*)" and pick the first suggestion'))
def enter_employee_name(admin_add_user_page, prefix) -> None:
    admin_add_user_page.enter_employee_name(prefix)


@when(parsers.re(r'I select the Status "(?P<status>[^"]*)"'))
def select_status(admin_add_user_page, status) -> None:
    admin_add_user_page.select_status(status)


@when("I enter a run-unique username in the Username field")
def enter_unique_username(admin_add_user_page, unique_username, created_username) -> None:
    created_username["value"] = unique_username
    admin_add_user_page.enter_username(unique_username)


@when(parsers.re(r'I enter the password "(?P<password>[^"]*)" and confirm password "(?P<confirm>[^"]*)"'))
def enter_passwords(admin_add_user_page, password, confirm) -> None:
    admin_add_user_page.enter_password(password)
    admin_add_user_page.enter_confirm_password(confirm)


@when("I click the Save button")
def click_save(admin_add_user_page) -> None:
    admin_add_user_page.click_save()


# ─────────────────────────────────────────────────────────────
# When — search
# ─────────────────────────────────────────────────────────────

@when("I search the Users list for the created username")
def search_created_username(admin_users_page, created_username) -> None:
    username = created_username["value"]
    assert username, "No created username recorded to search for"
    admin_users_page.search_by_username(username)


@when(parsers.re(r'I search the Users list for the username "(?P<username>[^"]*)"'))
def search_literal_username(admin_users_page, username) -> None:
    admin_users_page.search_by_username(username)


# ─────────────────────────────────────────────────────────────
# When — delete flow
# ─────────────────────────────────────────────────────────────

@when("I click the delete icon on the single result row")
def click_delete_icon(admin_users_page) -> None:
    assert admin_users_page.get_record_count() == 1, (
        "Expected exactly one result row before deleting"
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
    assert not admin_add_user_page.has_field_error(), (
        f"Form was rejected client-side: {admin_add_user_page.get_all_field_errors()}"
    )
    toast = admin_add_user_page.get_toast_text()
    assert toast, "Expected a success toast after saving the user"


@then(parsers.re(r'the results summary should read "(?P<expected>[^"]*)"'))
def assert_results_summary(admin_users_page, expected) -> None:
    if "No Records" in expected:
        assert admin_users_page.has_no_records(), "Expected the no-records indicator"
        return
    admin_users_page.wait_for_records_summary(expected)
    actual = admin_users_page.get_records_summary()
    assert expected in actual, f"Expected {expected!r} in results summary, got {actual!r}"


@then("the single result row should contain the created username")
def assert_row_contains_username(admin_users_page, created_username) -> None:
    username = created_username["value"]
    row_text = admin_users_page.get_row_username()
    assert username in row_text, f"Expected {username!r} in row text {row_text!r}"


@then("the delete confirmation dialog should be displayed")
def assert_dialog_displayed(admin_users_page) -> None:
    assert admin_users_page.is_delete_dialog_open(), "Delete confirmation dialog was not displayed"
    assert "Delete" in admin_users_page.get_confirm_button_text(), (
        "Confirm button did not offer a delete action"
    )


@then("no result rows should be displayed")
def assert_no_rows(admin_users_page) -> None:
    assert admin_users_page.has_no_records(), "Expected the no-records indicator"
