"""
Step definitions for features/login_validation.feature.
Each @given/@when/@then maps an English line to a Python action.
"""
import pytest
from pytest_bdd import scenarios, given, when, then, parsers

from pages.login_page import LoginPage
from pages.inventory_page import InventoryPage
from config.paths import feature_path


# Bind this test module to the feature file
scenarios(str(feature_path("login_validation")))


# === Page Object fixtures (created per-test) ===

@pytest.fixture
def login_page(page) -> LoginPage:
    return LoginPage(page)


@pytest.fixture
def inventory_page(page) -> InventoryPage:
    return InventoryPage(page)


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
    login_page.page.locator(LoginPage.ERROR_MESSAGE).locator("button").click()


@when(parsers.re(
    r'I clear the username field and enter "(?P<username>[^"]*)"'
))
def clear_and_enter_username(login_page: LoginPage, username: str) -> None:
    login_page.page.fill(LoginPage.USERNAME_INPUT, username)


@when(parsers.re(
    r'I clear the password field and enter "(?P<password>[^"]*)"'
))
def clear_and_enter_password(login_page: LoginPage, password: str) -> None:
    login_page.page.fill(LoginPage.PASSWORD_INPUT, password)


@when("I click the Login button")
def click_login(login_page: LoginPage) -> None:
    login_page.page.click(LoginPage.LOGIN_BUTTON)


# === THEN steps ===

@then("I should be redirected to the inventory page")
def verify_inventory_page(inventory_page: InventoryPage) -> None:
    assert inventory_page.is_loaded(), \
        f"Expected inventory page, but URL is: {inventory_page.page.url}"


@then(parsers.parse('I should see the page title "{expected_title}"'))
def verify_page_title(inventory_page: InventoryPage, expected_title: str) -> None:
    actual = inventory_page.get_page_title_text()
    assert actual == expected_title, \
        f"Expected title '{expected_title}', but got '{actual}'"


@then(parsers.parse('I should see the error message "{expected_message}"'))
def verify_error_message(login_page: LoginPage, expected_message: str) -> None:
    actual = login_page.get_error_message()
    assert actual == expected_message, \
        f"Expected error '{expected_message}', but got '{actual}'"


@then("I should remain on the login page")
def verify_still_on_login_page(login_page: LoginPage, base_url: str) -> None:
    actual_url = login_page.page.url.rstrip("/")
    expected_url = base_url.rstrip("/")
    assert actual_url == expected_url, \
        f"Expected to remain on login page '{expected_url}', but URL is '{actual_url}'"


@then("the error message should not be visible")
def verify_error_not_visible(login_page: LoginPage) -> None:
    assert not login_page.is_visible(LoginPage.ERROR_MESSAGE), \
        "Expected error message to be dismissed, but it is still visible"
