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
from pytest_bdd import scenarios, given, when, then, parsers

from config.paths import feature_path


# Bind this module to its feature file.
scenarios(str(feature_path("login")))


# === GIVEN steps ===

@given("I am on the SauceDemo login page")
def open_login_page(login_page, base_url):
    login_page.open(base_url)


# === WHEN steps ===

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
def login_with_credentials(login_page, username, password):
    login_page.login_as(username, password)


@when("I dismiss the error message")
def dismiss_error_banner(login_page):
    login_page.dismiss_error()


@when("I clear the credential fields")
def clear_credential_fields(login_page):
    login_page.clear_credentials()


# === THEN steps ===

@then("I should be redirected to the inventory page")
def verify_inventory_page(inventory_page):
    assert inventory_page.is_loaded(), \
        f"Expected inventory page, but URL is: {inventory_page.page.url}"


@then(parsers.re(r'I should see the page title "(?P<expected_title>[^"]*)"'))
def verify_page_title(inventory_page, expected_title):
    actual = inventory_page.get_page_title_text()
    assert actual == expected_title, \
        f"Expected title '{expected_title}', but got '{actual}'"


@then(parsers.re(r'I should see the error message "(?P<expected_message>[^"]*)"'))
def verify_error_message(login_page, expected_message):
    actual = login_page.get_error_message()
    assert actual == expected_message, \
        f"Expected error '{expected_message}', but got '{actual}'"


@then("no error message should be displayed")
def verify_no_error_message(login_page):
    actual = login_page.get_error_message()
    assert actual == "", \
        f"Expected no error message, but got '{actual}'"