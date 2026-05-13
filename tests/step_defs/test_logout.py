"""
Step definitions for features/logout.feature.
Each @given/@when/@then maps an English line to a Python action.
"""
import pytest
from pytest_bdd import scenarios, given, when, then, parsers

from pages.login_page import LoginPage
from pages.inventory_page import InventoryPage
from config.paths import feature_path


# Bind this test module to the feature file
scenarios(str(feature_path("logout")))


# === Page Object fixtures (created per-test) ===

@pytest.fixture
def login_page(page):
    return LoginPage(page)


@pytest.fixture
def inventory_page(page):
    # NOTE: The burger menu, logout link, and inventory container selectors are not
    # exposed via methods in the provided POM definition for visibility checks.
    # We add them here as class attributes to make the step definitions work.
    # In a real project, these would be added to pages/inventory_page.py.
    InventoryPage.BURGER_MENU_BUTTON = "#react-burger-menu-btn"
    InventoryPage.LOGOUT_LINK = "[data-test='logout-sidebar-link']"
    InventoryPage.INVENTORY_CONTAINER = "[data-test='inventory-container']"
    return InventoryPage(page)


# === GIVEN steps ===

@given("I am logged in as a standard user")
def logged_in_standard_user(login_page: LoginPage, inventory_page: InventoryPage, base_url: str):
    """
    A composite step to log in the standard user and verify they are on the
    inventory page. This is a common precondition for many tests.
    """
    login_page.open(base_url)
    login_page.login_as("standard_user", "secret_sauce")
    assert inventory_page.is_loaded(), "Failed to log in or load inventory page."


# === WHEN steps ===

@when("I log out from the application")
def log_out(inventory_page: InventoryPage):
    """Logs the user out using the composite logout method."""
    inventory_page.logout()


@when("I open the burger menu")
def open_burger_menu(inventory_page: InventoryPage):
    """Opens the burger menu."""
    inventory_page.open_burger_menu()


@when("I click the logout link")
def click_logout_link(inventory_page: InventoryPage):
    """Clicks the logout link from the sidebar menu."""
    inventory_page.click_logout()


@when("I navigate directly to the inventory page")
def navigate_to_inventory(inventory_page: InventoryPage, base_url: str):
    """Navigates directly to the inventory page URL."""
    inventory_url = f"{base_url.rstrip('/')}/inventory.html"
    inventory_page.navigate(inventory_url)


@when("I click the browser's back button")
def click_browser_back(inventory_page: InventoryPage):
    """Uses the browser's back navigation."""
    inventory_page.go_back()


# === THEN steps ===

@then("I should be on the login page")
@then("I should be redirected to the login page")
def verify_on_login_page(login_page: LoginPage, base_url: str):
    """Verifies the user is on the login page by checking URL and a key element."""
    actual_url = login_page.page.url.rstrip('/')
    expected_url = base_url.rstrip('/')
    assert actual_url == expected_url, \
        f"Expected to be on login page '{expected_url}', but was on '{actual_url}'."

    assert login_page.is_visible(LoginPage.LOGIN_BUTTON), \
        "Login button not visible, may not be on the login page."


@then("I should remain on the login page")
def remain_on_login_page(login_page: LoginPage, base_url: str):
    """
    Verifies the user is still on the login page. This has the same logic as
    verifying the initial redirect, so we reuse that function.
    """
    verify_on_login_page(login_page, base_url)


@then(parsers.parse('I should see the error message "{expected_message}"'))
def verify_error_message(login_page: LoginPage, expected_message: str):
    """Verifies that a specific error message is displayed."""
    actual = login_page.get_error_message()
    assert actual == expected_message, \
        f"Expected error '{expected_message}', but got '{actual}'"


@then("the burger menu should be visible")
def verify_burger_menu_visible(inventory_page: InventoryPage):
    """Verifies the burger menu icon is visible on the page."""
    assert inventory_page.is_visible(inventory_page.BURGER_MENU_BUTTON), \
        "Burger menu button is not visible."


@then("the logout link should be visible in the sidebar")
def verify_logout_link_visible(inventory_page: InventoryPage):
    """Verifies the logout link is visible after opening the burger menu."""
    assert inventory_page.is_visible(inventory_page.LOGOUT_LINK), \
        "Logout link is not visible in the sidebar."


@then("the username field should be empty")
def verify_username_field_empty(login_page: LoginPage):
    """Verifies the username input field is empty."""
    username_value = login_page.page.input_value(LoginPage.USERNAME_INPUT)
    assert username_value == "", \
        f"Expected username field to be empty, but it contained '{username_value}'."


@then("the password field should be empty")
def verify_password_field_empty(login_page: LoginPage):
    """Verifies the password input field is empty."""
    password_value = login_page.page.input_value(LoginPage.PASSWORD_INPUT)
    assert password_value == "", \
        f"Expected password field to be empty, but it was not."


@then("the inventory page should not be visible")
def verify_inventory_page_not_visible(inventory_page: InventoryPage):
    """
    Verifies that the main content of the inventory page is not visible,
    confirming the user was not taken back to a cached, logged-in state.
    """
    assert not inventory_page.is_visible(inventory_page.INVENTORY_CONTAINER), \
        "Inventory page content is visible after logging out and using back button."
