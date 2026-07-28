"""Step definitions for features/login.feature.

REFERENCE FILE — Agent 2 copies this style. Rules it demonstrates:

- Declare EVERY step your feature uses in this file. Steps are module-scoped,
  so a step defined in another step-def module is not visible here.
- Call page-object methods only. Never put a selector in a step definition.
- Keep each decorator pattern on ONE line.
- Use parsers.re with [^"]* where a quoted value could be empty; parsers.parse
  cannot match "".
- Log in by ROLE via the `credentials` fixture. Invalid data (empty values,
  wrong passwords) stays literal — it is test data, not a credential.
"""
from pytest_bdd import given, when, then, parsers, scenarios

from config.paths import feature_path

scenarios(str(feature_path("login")))


# ─────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────

@given("I am on the OrangeHRM login page")
def open_login_page(login_page, base_url):
    login_page.open(base_url)


# ─────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────

@when(parsers.re(r'I log in as "(?P<role>[^"]*)"$'))
def login_as_role(login_page, credentials, role):
    """Log in with real credentials resolved from the environment."""
    username, password = credentials(role)
    login_page.login_as(username, password)


@when(parsers.re(r'I log in as "(?P<role>[^"]*)" with an incorrect password'))
def login_as_role_wrong_password(login_page, credentials, role):
    """Valid username, deliberately wrong password (test data, not a secret)."""
    username, _ = credentials(role)
    login_page.login_as(username, "definitely-not-the-password")


@when(parsers.re(r'I log in with username "(?P<username>[^"]*)" and password "(?P<password>[^"]*)"'))
def login_with_literal_credentials(login_page, username, password):
    """Literal values, for invalid and empty-field scenarios."""
    login_page.login_as(username, password)


@when("I clear the credential fields")
def clear_credentials(login_page):
    login_page.clear_credentials()


# ─────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────

@then("I should be redirected to the dashboard")
def assert_on_dashboard(dashboard_page):
    assert dashboard_page.is_loaded(), "Dashboard did not load after login"


@then(parsers.re(r'I should see the page title "(?P<expected_title>[^"]*)"'))
def assert_page_title(dashboard_page, expected_title):
    actual = dashboard_page.get_header_title()
    assert actual == expected_title, f"Expected title {expected_title!r}, got {actual!r}"


@then(parsers.re(r'I should see the error message "(?P<expected_message>[^"]*)"'))
def assert_error_message(login_page, expected_message):
    actual = login_page.get_error_message()
    assert expected_message in actual, f"Expected {expected_message!r} in {actual!r}"


@then(parsers.re(r'I should see the field error "(?P<expected_message>[^"]*)"'))
def assert_field_error(login_page, expected_message):
    actual = login_page.get_field_error()
    assert expected_message in actual, f"Expected {expected_message!r} in {actual!r}"


@then("I should remain on the login page")
def assert_still_on_login(login_page):
    assert login_page.is_login_form_displayed(), "Expected to stay on the login page"
