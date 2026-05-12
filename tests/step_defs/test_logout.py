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

@given(parsers.parse('I am logged in as "{username}"'))
def logged_in(login_page, inventory_page, base_url, username):
    """Logs the user in and verifies they are on the inventory page."""
    # For this test suite, all test users share the same password
    password = "secret_sauce"
    login_page.open(base_url)
    login_page.login_as(username, password)
    assert inventory_page.is_loaded(), \
        "User failed to log in or was not redirected to inventory page."


# === WHEN steps ===

@when("I open the burger menu")
def open_burger_menu(inventory_page):
    """Opens the burger side menu."""
    inventory_page.open_burger_menu()


@when('I click the "Logout" link')
def click_logout_link(inventory_page):
    """Clicks the logout link in the side menu."""
    inventory_page.click_logout_link()


@when("I log out")
def log_out(inventory_page):
    """Logs the user out using the burger menu."""
    inventory_page.logout()


@when("I navigate directly to the inventory page")
def navigate_to_inventory(inventory_page, base_url):
    """Directly navigates to the inventory page URL."""
    inventory_url = f"{base_url.rstrip('/')}/inventory.html"
    inventory_page.navigate(inventory_url)


@when("I press the browser back button")
def press_browser_back(inventory_page):
    """Navigates back using the browser's history."""
    inventory_page.go_back()


# === THEN steps ===

@then("I should be redirected to the login page")
@then("I should remain on the login page")
@then("I should be on the login page")
def verify_on_login_page(login_page, base_url):
    """Verifies the user is on the login page by checking URL and a key element."""
    current_url = login_page.page.url.rstrip('/')
    expected_url = base_url.rstrip('/')
    assert current_url == expected_url, \
        f"Expected to be on login page ({expected_url}), but was on {current_url}"
    assert login_page.is_visible(login_page.LOGIN_BUTTON), \
        "Login button not visible, may not be on login page."


@then("the burger menu should be visible")
def verify_burger_menu_visible(inventory_page):
    """Verifies the burger menu icon is visible."""
    assert inventory_page.is_visible(inventory_page.BURGER_MENU_BUTTON), \
        "Burger menu button was not visible on the inventory page."


@then("the side menu should be visible")
def verify_side_menu_visible(inventory_page):
    """Verifies the side menu container is visible after opening it."""
    assert inventory_page.is_visible(inventory_page.SIDE_MENU), \
        "Side menu was not visible after clicking the burger menu icon."


@then('the side menu should contain the "Logout" link')
def verify_logout_link_visible(inventory_page):
    """Verifies that the logout link is visible in the side menu."""
    assert inventory_page.is_visible(inventory_page.LOGOUT_LINK), \
        "Logout link was not visible in the side menu."


@then("the username input should be empty")
def verify_username_is_empty(login_page):
    """Verifies that the username input field is empty."""
    username_value = login_page.page.input_value(login_page.USERNAME_INPUT)
    assert username_value == "", \
        f"Username field was not empty, contained: '{username_value}'"


@then("the password input should be empty")
def verify_password_is_empty(login_page):
    """Verifies that the password input field is empty."""
    password_value = login_page.page.input_value(login_page.PASSWORD_INPUT)
    assert password_value == "", \
        "Password field was not empty."


@then("the username and password fields should be empty")
def verify_fields_empty(login_page):
    """Verifies that both username and password input fields are empty."""
    verify_username_is_empty(login_page)
    verify_password_is_empty(login_page)


@then(parsers.parse('I should see the error message "{expected_message}"'))
def verify_error_message(login_page, expected_message):
    """Verifies that a specific error message is displayed."""
    actual_message = login_page.get_error_message()
    assert actual_message == expected_message, \
        f"Expected error message '{expected_message}', but got '{actual_message}'"
