"""
Step definitions for features/inventory_menu_and_logout.feature.
Each @given/@when/@then maps an English line to a Python action.
"""
import pytest
from pytest_bdd import scenarios, given, when, then, parsers

from pages.login_page import LoginPage
from pages.inventory_page import InventoryPage
from pathlib import Path
from config.paths import feature_path


# Bind this test module to the feature file
scenarios(str(feature_path("inventory_menu_and_logout")))


# === Page Object fixtures (created per-test) ===

@pytest.fixture
def login_page(page):
    """Returns a LoginPage object."""
    return LoginPage(page)


@pytest.fixture
def inventory_page(page):
    """Returns an InventoryPage object."""
    return InventoryPage(page)


# === GIVEN steps ===

@given("I am on the SauceDemo login page")
def open_login_page(login_page: LoginPage, base_url: str):
    """Navigates to the SauceDemo login page."""
    login_page.open(base_url)


# === WHEN steps ===

@when(parsers.parse('I log in with username "{username}" and password "{password}"'))
def login_with_credentials(login_page: LoginPage, username: str, password: str):
    """Performs login with the given credentials."""
    login_page.login_as(username, password)


@when("I open the burger menu")
def open_burger_menu(inventory_page: InventoryPage):
    """Opens the burger menu on the inventory page."""
    inventory_page.open_burger_menu()


@when("I click the 'Logout' link")
def click_logout_link(inventory_page: InventoryPage):
    """Clicks the 'Logout' link in the navigation menu."""
    inventory_page.click_logout()


@when("I attempt to navigate directly to the inventory page")
def attempt_direct_inventory_access(inventory_page: InventoryPage, base_url: str):
    """Attempts to navigate directly to the inventory page URL."""
    inventory_page.page.goto(f"{base_url}/inventory.html")


# CRITICAL FIX: The validator indicated these steps were prefixed with 'When' in the feature file.
# Changed decorators from @then to @when to match the feature file's Gherkin keyword.
@when("I should be redirected to the inventory page")
def verify_inventory_page(inventory_page: InventoryPage):
    """Verifies that the current page is the inventory page."""
    assert inventory_page.is_loaded(), \
        f"Expected to be on inventory page, but URL is: {inventory_page.page.url}"


@when(parsers.parse('I should see the page title "{expected_title}"'))
def verify_page_title(inventory_page: InventoryPage, expected_title: str):
    """Verifies the text of the page title."""
    actual = inventory_page.get_page_title_text()
    assert actual == expected_title, \
        f"Expected title '{expected_title}', but got '{actual}'"


# === THEN steps ===

@then("I should see the burger menu icon")
def burger_menu_icon_visible(inventory_page: InventoryPage):
    """Verifies that the burger menu icon is visible on the inventory page."""
    assert inventory_page.is_burger_menu_button_visible(), \
        "Expected burger menu icon to be visible, but it was not."


@then("I should see the 'Logout' link in the burger menu")
def logout_link_visible_in_menu(inventory_page: InventoryPage):
    """Verifies that the 'Logout' link is visible within the opened navigation menu."""
    assert inventory_page.is_logout_link_visible(), \
        "Expected 'Logout' link to be visible in the menu, but it was not."


@then("I should be redirected to the login page")
def redirected_to_login_page(login_page: LoginPage, base_url: str):
    """Verifies that the current page is the login page."""
    assert login_page.page.url == base_url, \
        f"Expected to be on login page (URL: {base_url}), but current URL is: {login_page.page.url}"
    assert login_page.is_visible(login_page.LOGIN_BUTTON), \
        "Expected login button to be visible on the login page, but it was not."


@then(parsers.parse('I should see the error message "{expected_message}"'))
def verify_error_message(login_page: LoginPage, expected_message: str):
    """Verifies that a specific error message is displayed on the login page."""
    actual = login_page.get_error_message()
    assert actual == expected_message, \
        f"Expected error message '{expected_message}', but got '{actual}'"


@then("I should see the username and password input fields")
def login_form_fields_visible(login_page: LoginPage):
    """Verifies that the username and password input fields are visible on the login page."""
    assert login_page.is_visible(login_page.USERNAME_INPUT), \
        "Expected username input field to be visible, but it was not."
    assert login_page.is_visible(login_page.PASSWORD_INPUT), \
        "Expected password input field to be visible, but it was not."
