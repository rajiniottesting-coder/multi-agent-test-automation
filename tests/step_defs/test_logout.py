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
    return InventoryPage(page)


# === GIVEN steps ===

@given("I am logged in as a standard user")
def logged_in_standard_user(login_page, inventory_page, base_url):
    """Precondition: Log in as a standard user and verify landing on the inventory page."""
    login_page.open(base_url)
    login_page.login_as("standard_user", "secret_sauce")
    assert inventory_page.is_loaded(), "Failed to load inventory page after login."


# === WHEN steps ===

@when("I open the burger menu")
def open_burger_menu(inventory_page):
    """Click the burger menu icon to open the sidebar."""
    inventory_page.open_burger_menu()


@when("I click the logout link")
def click_logout_link(inventory_page):
    """Click the logout link in the sidebar menu."""
    inventory_page.click_logout_link()


@when("I navigate directly to the inventory page")
def navigate_to_inventory(page, base_url):
    """Try to access a protected page by URL after logging out."""
    inventory_page_url = base_url.rstrip('/') + "/inventory.html"
    page.goto(inventory_page_url)


# === THEN steps ===

@then("I should be redirected to the login page")
def verify_on_login_page(login_page):
    """Verify the user is on the login page by checking for a key element."""
    # A simple URL check is also good, but checking for a key element
    # confirms the page has started rendering.
    assert login_page.is_visible(login_page.LOGIN_BUTTON), \
        f"Expected to be on login page, but URL is {login_page.page.url}"


@then("the login form should be visible")
def verify_login_form_visible(login_page):
    """Verify the username and password fields are visible."""
    assert login_page.is_visible(login_page.USERNAME_INPUT), "Username input is not visible."
    assert login_page.is_visible(login_page.PASSWORD_INPUT), "Password input is not visible."


@then("the logout link should be visible")
def verify_logout_link_visible(inventory_page):
    """Verify the logout link is visible in the sidebar menu."""
    # This selector is standard for SauceDemo. A dedicated method could be added
    # to the InventoryPage POM, e.g., `is_logout_link_visible()`.
    logout_link_selector = "[data-test='logout-sidebar-link']"
    assert inventory_page.is_visible(logout_link_selector), "Logout link is not visible in the burger menu."


@then(parsers.parse('I should see the error message "{expected_message}"'))
def verify_error_message(login_page, expected_message):
    """Verify that a specific error message is displayed on the login page."""
    actual = login_page.get_error_message()
    assert actual == expected_message, \
        f"Expected error '{expected_message}', but got '{actual}'"
