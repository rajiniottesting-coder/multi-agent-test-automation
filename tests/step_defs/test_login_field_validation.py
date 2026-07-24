"""Step definitions for features/login_field_validation.feature.

Covers empty fields, whitespace-only input, and validation error assertions.
Uses parsers.re for steps that may receive empty quoted values.
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

@when(parsers.re(r'I log in with username "(?P<username>[^"]*)" and password "(?P<password>[^"]*)"'))
def login_with_credentials(login_page, username: str, password: str) -> None:
    login_page.login_as(username, password)


@when(parsers.re(r'I log in as "(?P<role>[^"]*)" with an empty password'))
def login_as_role_empty_password(login_page, credentials, role: str) -> None:
    """Log in with a valid username resolved from the environment but an empty password."""
    username, _ = credentials(role)
    login_page.login_as(username, "")


@when("I dismiss the error message")
def dismiss_error_banner(login_page) -> None:
    login_page.dismiss_error()


@when("I clear the credential fields")
def clear_credential_fields(login_page) -> None:
    login_page.clear_credentials()


# === THEN steps ===

@then(parsers.re(r'I should see the error message "(?P<expected_message>[^"]*)"'))
def verify_error_message(login_page, expected_message: str) -> None:
    actual = login_page.get_error_message()
    assert actual == expected_message, \
        f"Expected error '{expected_message}', but got '{actual}'"
