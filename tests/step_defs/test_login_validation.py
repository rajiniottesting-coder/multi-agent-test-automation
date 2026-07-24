"""Step definitions for features/login_validation.feature.

Covers literal credential entry, error message assertions, and error dismissal.
Steps are module-scoped so every step used by the feature MUST be declared here,
even if an identical step text exists in another step-def module.

Invalid data (empty strings, whitespace, wrong passwords) stays literal in the
feature file — it is test data, not a credential.
"""
from pytest_bdd import scenarios, given, when, then, parsers

from config.paths import feature_path


# Bind this module to its feature file.
scenarios(str(feature_path("login_validation")))


# === GIVEN steps ===

@given("I am on the SauceDemo login page")
def open_login_page(login_page, base_url) -> None:
    login_page.open(base_url)


# === WHEN steps ===

@when(parsers.re(r'I log in with username "(?P<username>[^"]*)" and password "(?P<password>[^"]*)"'))
def login_with_credentials(login_page, username: str, password: str) -> None:
    """Log in with literal username and password values (may be empty or whitespace)."""
    login_page.login_as(username, password)


@when("I dismiss the error message")
def dismiss_error_banner(login_page) -> None:
    login_page.dismiss_error()


@when("I clear the credential fields")
def clear_credential_fields(login_page) -> None:
    login_page.clear_credentials()


@when("I click the LOGIN button")
def click_login_button(login_page) -> None:
    """Click the login button without entering any credentials."""
    login_page.login_as("", "")


# === THEN steps ===

@then(parsers.re(r'I should see the error message "(?P<expected_message>[^"]*)"'))
def verify_error_message(login_page, expected_message: str) -> None:
    actual = login_page.get_error_message()
    assert actual == expected_message, \
        f"Expected error '{expected_message}', but got '{actual}'"


@then("no error message should be displayed")
def verify_no_error_message(login_page) -> None:
    actual = login_page.get_error_message()
    assert actual == "", \
        f"Expected no error message, but got '{actual}'"


@then("I should remain on the login page")
def verify_still_on_login_page(login_page, base_url) -> None:
    actual_url = login_page.page.url.rstrip("/")
    expected_url = base_url.rstrip("/")
    assert actual_url == expected_url, \
        f"Expected to remain on login page '{expected_url}', but URL is '{actual_url}'"


@then(parsers.re(r'I should see the login error "(?P<expected_message>[^"]*)"'))
def verify_login_error(login_page, expected_message: str) -> None:
    actual = login_page.get_error_message()
    assert actual == expected_message, \
        f"Expected error '{expected_message}', but got '{actual}'"


@then(parsers.re(r'the login error should contain "(?P<substring>[^"]*)"'))
def verify_error_contains(login_page, substring: str) -> None:
    actual = login_page.get_error_message()
    assert substring in actual, \
        f"Expected error to contain '{substring}', but got '{actual}'"
