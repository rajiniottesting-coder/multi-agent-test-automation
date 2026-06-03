"""
Step definitions for features/login_edge_validation.feature.
Each @given/@when/@then maps an English line to a Python action.
"""
import pytest
from pytest_bdd import scenarios, given, when, then, parsers

from pages.login_page import LoginPage
from config.paths import feature_path


# Bind this test module to the feature file
scenarios(str(feature_path("login_edge_validation")))


# === Page Object fixtures (created per-test) ===

@pytest.fixture
def login_page(page) -> LoginPage:
    return LoginPage(page)


# === GIVEN steps ===

@given("I am on the SauceDemo login page")
def open_login_page(login_page: LoginPage, base_url: str) -> None:
    login_page.open(base_url)


# === WHEN steps ===

@when(parsers.re(
    r'I log in with username "(?P<username>[^"]*)" and password "(?P<password>[^"]*)"'
))
def login_with_credentials(login_page: LoginPage, username: str, password: str) -> None:
    login_page.login_as(username, password)


@when("I dismiss the error message")
def dismiss_error(login_page: LoginPage) -> None:
    # Use the error message locator defined on LoginPage and click its close button
    error_button = login_page.page.locator(LoginPage.ERROR_MESSAGE).locator("button")
    error_button.click()


@when("I clear the username and password fields")
def clear_fields(login_page: LoginPage) -> None:
    login_page.page.fill(LoginPage.USERNAME_INPUT, "")
    login_page.page.fill(LoginPage.PASSWORD_INPUT, "")


# === THEN steps ===

@then(parsers.parse('I should see the error message "{expected_message}"'))
def verify_error_message(login_page: LoginPage, expected_message: str) -> None:
    actual = login_page.get_error_message()
    assert actual == expected_message, \
        f"Expected error '{expected_message}', but got '{actual}'"


@then("I should remain on the login page")
def verify_on_login_page(login_page: LoginPage, base_url: str) -> None:
    actual_url = login_page.page.url.rstrip("/")
    expected_url = base_url.rstrip("/")
    assert actual_url == expected_url, \
        f"Expected to remain on login page '{expected_url}', but URL is '{actual_url}'"


@then("the error message should not be visible")
def verify_error_not_visible(login_page: LoginPage) -> None:
    visible = login_page.is_visible(LoginPage.ERROR_MESSAGE)
    assert not visible, \
        "Expected error message to not be visible, but it is still displayed"
