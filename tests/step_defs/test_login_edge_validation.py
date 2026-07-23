"""
Step definitions for features/login_edge_validation.feature.

Self-contained module: declares every step its feature file uses.
Steps that share phrasing with other modules are re-declared here
intentionally — pytest-bdd step definitions are module-scoped.

Page-object FIXTURES come from tests/step_defs/conftest.py.
"""
from urllib.parse import urlparse

from pytest_bdd import scenarios, given, when, then, parsers

from config.paths import feature_path


# Bind this module to its feature file.
scenarios(str(feature_path("login_edge_validation")))


# === GIVEN steps ===

@given("I am on the SauceDemo login page")
def open_login_page(login_page, base_url: str) -> None:
    login_page.open(base_url)


# === WHEN steps ===

@when(
    parsers.re(
        r'I log in with username "(?P<username>[^"]*)" and password "(?P<password>[^"]*)"'
    )
)
def login_with_credentials(login_page, username: str, password: str) -> None:
    login_page.login_as(username, password)


@when("I dismiss the error message")
def dismiss_error_banner(login_page) -> None:
    login_page.dismiss_error()


@when("I clear the credential fields")
def clear_credential_fields(login_page) -> None:
    login_page.clear_credentials()


# === THEN steps ===

@then("I should be redirected to the inventory page")
def verify_inventory_page(inventory_page) -> None:
    assert inventory_page.is_loaded(), \
        f"Expected inventory page, but URL is: {inventory_page.page.url}"


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


@then(parsers.re(r'I should see an error message containing "(?P<partial_message>[^"]*)"'))
def verify_error_message_contains(login_page, partial_message: str) -> None:
    actual = login_page.get_error_message()
    assert partial_message in actual, \
        f"Expected error containing '{partial_message}', but got '{actual}'"


@then("I should remain on the login page")
def verify_still_on_login_page(login_page, base_url: str) -> None:
    current_path = urlparse(login_page.page.url).path
    assert current_path.rstrip("/") == "" or current_path == "/", \
        f"Expected to remain on login page (/), but current path is: {current_path}"


@then(parsers.parse("I should see {count:d} inventory items"))
def verify_inventory_item_count(inventory_page, count: int) -> None:
    actual = inventory_page.get_item_count()
    assert actual == count, \
        f"Expected {count} inventory items, but got {actual}"
