"""
Step definitions for features/logout.feature.
Each @given/@when/@then maps an English line to a Python action.
"""
import pytest
from pytest_bdd import scenarios, given, when, then, parsers

from pages.login_page import LoginPage
from pages.inventory_page import InventoryPage
from pathlib import Path
from config.paths import feature_path


# Bind this test module to the feature file
scenarios(str(feature_path("logout")))


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
    """Navigates to the SauceDemo login page."""
    login_page.open(base_url)


# === WHEN steps ===

@when(parsers.parse('I log in with username "{username}" and password "{password}"'))
def login_with_credentials(login_page, username, password):
    """Logs in with the specified username and password."""
    login_page.login_as(username, password)


@when("I open the burger menu")
def open_burger_menu(inventory_page):
    """Clicks the burger menu icon to open the navigation sidebar."""
    inventory_page.open_burger_menu()


@when('I click the "Logout" option')
def click_logout_option(inventory_page):
    """Clicks the 'Logout' link within the navigation sidebar."""
    inventory_page.click_logout_link()


@when("I attempt to navigate directly to the inventory page")
def attempt_direct_inventory_access(inventory_page, base_url):
    """Attempts to navigate directly to the inventory page URL."""
    inventory_page.navigate(f"{base_url}/inventory.html")


# === THEN steps ===

@then("I should be redirected to the inventory page")
def verify_inventory_page(inventory_page):
    """Verifies that the user is currently on the inventory page."""
    assert inventory_page.is_loaded(), \
        f"Expected inventory page, but URL is: {inventory_page.page.url}"


@then('I should see the "Logout" option in the burger menu')
def verify_logout_option_visible(inventory_page):
    """Verifies that the 'Logout' link is visible in the opened navigation menu."""
    assert inventory_page.is_logout_link_in_menu_visible(), \
        "Logout option should be visible in the opened burger menu."


@then("I should see the username and password input fields")
def verify_login_form_fields_visible(login_page):
    """Verifies that the username, password, and login button fields are visible."""
    assert login_page.are_login_form_fields_visible(), \
        "Login form fields (username, password, login button) should be visible."


@then("I should be redirected to the login page")
def verify_redirect_to_login(login_page):
    """Verifies that the user is currently on the login page."""
    assert login_page.is_loaded(), \
        f"Expected to be on login page, but current URL is {login_page.page.url}"


@then(parsers.parse('I should see the error message "{expected_message}"'))
def verify_error_message(login_page, expected_message):
    """Verifies that the specified error message is displayed on the login page."""
    actual = login_page.get_error_message()
    assert actual == expected_message, \
        f"Expected error '{expected_message}', but got '{actual}'"
