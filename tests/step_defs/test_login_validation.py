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
def login_page(page):
    return LoginPage(page)


@pytest.fixture
def inventory_page(page):
    return InventoryPage(page)


# === GIVEN steps ===

@given("I am on the SauceDemo login page")
def open_login_page(login_page, base_url):
    login_page.open(base_url)


# === WHEN steps ===

@when(parsers.re(
    r'I log in with username "(?P<username>[^"]*)" and password "(?P<password>[^"]*)"'
))
def login_with_credentials(login_page, username, password):
    """Perform login with the given username and password (supports empty strings)."""
    login_page.login_as(username, password)


@when(parsers.re(
    r'I enter "(?P<username>[^"]*)" into the username field'
))
def enter_username(login_page, username):
    """Type a value into the username field."""
    login_page.page.fill(login_page.USERNAME_INPUT, username)


@when(parsers.re(
    r'I enter "(?P<password>[^"]*)" into the password field'
))
def enter_password(login_page, password):
    """Type a value into the password field."""
    login_page.page.fill(login_page.PASSWORD_INPUT, password)


@when("I click the Login button")
def click_login(login_page):
    login_page.page.click(login_page.LOGIN_BUTTON)


@when("I clear the username field")
def clear_username(login_page):
    login_page.page.fill(login_page.USERNAME_INPUT, "")


@when("I clear the password field")
def clear_password(login_page):
    login_page.page.fill(login_page.PASSWORD_INPUT, "")


@when("I dismiss the error message")
def dismiss_error_message(login_page):
    """Click the X button on the error message banner to dismiss it."""
    close_button = login_page.page.locator("[data-test='error'] button.error-button")
    close_button.click()


# === THEN steps ===

@then("I should be redirected to the inventory page")
def verify_inventory_page(inventory_page):
    assert inventory_page.is_loaded(), \
        f"Expected inventory page, but URL is: {inventory_page.page.url}"


@then(parsers.parse('I should see the page title "{expected_title}"'))
def verify_page_title(inventory_page, expected_title):
    actual = inventory_page.get_page_title_text()
    assert actual == expected_title, \
        f"Expected title '{expected_title}', but got '{actual}'"


@then(parsers.parse('I should see the error message "{expected_message}"'))
def verify_error_message(login_page, expected_message):
    actual = login_page.get_error_message()
    assert actual == expected_message, \
        f"Expected error '{expected_message}', but got '{actual}'"


@then("I should remain on the login page")
def verify_still_on_login_page(login_page, base_url):
    current_url = login_page.page.url.rstrip("/")
    expected_url = base_url.rstrip("/")
    assert current_url == expected_url, \
        f"Expected to remain on login page '{expected_url}', but URL is '{current_url}'"


@then("the error message should not be visible")
def verify_error_not_visible(login_page):
    login_page.page.locator(login_page.ERROR_MESSAGE).wait_for(state="hidden", timeout=5000)
    visible = login_page.is_visible(login_page.ERROR_MESSAGE)
    assert not visible, \
        "Expected error message to be dismissed, but it is still visible"
