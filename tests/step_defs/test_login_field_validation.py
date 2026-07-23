"""
Step definitions for features/login_field_validation.feature.

This module is SELF-CONTAINED: it declares EVERY step its own feature file
uses. Steps that also appear in other modules (e.g. test_login.py) are
re-declared here because pytest-bdd step definitions are module-scoped
fixtures and another module's steps are invisible to this one.

Page-object FIXTURES (login_page, inventory_page) come from
tests/step_defs/conftest.py via pytest's hierarchical fixture resolution.
"""
from pytest_bdd import scenarios, given, when, then, parsers

from config.paths import feature_path


# Bind this module to its feature file.
scenarios(str(feature_path("login_field_validation")))


# === GIVEN steps ===

@given("I am on the SauceDemo login page")
def open_login_page(login_page, base_url) -> None:
    login_page.open(base_url)


# === WHEN steps ===

@when(parsers.re(
    r'I log in with username "(?P<username>[^"]*)" and password "(?P<password>[^"]*)"'
))
def login_with_credentials(login_page, username: str, password: str) -> None:
    login_page.login_as(username, password)


@when("I dismiss the error message")
def dismiss_error_banner(login_page) -> None:
    login_page.dismiss_error()


@when("I clear the credential fields")
def clear_credential_fields(login_page) -> None:
    login_page.clear_credentials()


# === THEN steps ===

@then(parsers.re(
    r'I should see the error message "(?P<expected_message>[^"]*)"'
))
def verify_error_message(login_page, expected_message: str) -> None:
    actual = login_page.get_error_message()
    assert actual == expected_message, \
        f"Expected error '{expected_message}', but got '{actual}'"


@then("I should not be logged in")
def verify_not_logged_in(login_page, base_url) -> None:
    actual_url = login_page.page.url.rstrip("/")
    expected_url = base_url.rstrip("/")
    assert actual_url == expected_url, \
        f"Expected to remain on login page '{expected_url}', but URL is '{actual_url}'"


@then(parsers.re(
    r'I should see an error matching either "(?P<option_a>[^"]*)" or "(?P<option_b>[^"]*)"'
))
def verify_error_message_one_of_two(login_page, option_a: str, option_b: str) -> None:
    actual = login_page.get_error_message()
    assert actual in (option_a, option_b), \
        f"Expected error to be either '{option_a}' or '{option_b}', but got '{actual}'"


@then("I should see a login error")
def verify_login_error_present(login_page) -> None:
    actual = login_page.get_error_message()
    assert actual != "", \
        "Expected a login error message to be displayed, but none was found"
