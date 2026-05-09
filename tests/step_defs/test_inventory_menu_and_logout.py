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
    """
    Navigates to the SauceDemo login page.
    """
    login_page.open(base_url)


@given(parsers.parse('I am logged in as "{username}" with password "{password}"'))
def logged_in_user(login_page: LoginPage, inventory_page: InventoryPage, base_url: str, username: str, password: str):
    """
    Logs in a user with the given credentials and verifies redirection to the inventory page.
    """
    login_page.open(base_url)
    login_page.login_as(username, password)
    assert inventory_page.is_loaded(), \
        f"Expected to be on inventory page after login, but URL is: {inventory_page.page.url}"


@given("I am on the inventory page")
def on_inventory_page(inventory_page: InventoryPage):
    """
    Verifies that the user is currently on the inventory page.
    This step assumes the user is already logged in and redirected.
    """
    assert inventory_page.is_loaded(), \
        f"Expected to be on inventory page, but URL is: {inventory_page.page.url}"


# === WHEN steps ===

@when(parsers.re(r'I log in with username "(?P<username>[^"]*)" and password "(?P<password>[^"]*)"'))
def login_with_credentials(login_page: LoginPage, username: str, password: str):
    """
    Performs a login action with the given credentials.
    Uses parsers.re to handle potentially empty username/password strings.
    """
    login_page.login_as(username, password)


@when("I click the burger menu icon")
def click_burger_menu(inventory_page: InventoryPage):
    """
    Clicks the burger menu button on the inventory page.
    """
    inventory_page.click_burger_menu_button()


@when(parsers.parse('I click the "{link_text}" link'))
def click_menu_link(inventory_page: InventoryPage, link_text: str):
    """
    Clicks a specific link within the opened burger menu.
    Currently only supports 'Logout'.
    """
    if link_text == "Logout":
        inventory_page.click_logout_link()
    else:
        pytest.fail(f"Unsupported menu link: {link_text}. Only 'Logout' is implemented.")


@when("I attempt to navigate directly to the inventory page")
def attempt_direct_inventory_access(page, base_url: str):
    """
    Attempts to navigate directly to the inventory page URL.
    """
    page.goto(f"{base_url}/inventory.html")


# === THEN steps ===

@then("I should be redirected to the inventory page")
def verify_redirect_to_inventory_page(inventory_page: InventoryPage):
    """
    Verifies that the current page is the inventory page.
    """
    assert inventory_page.is_loaded(), \
        f"Expected to be redirected to inventory page, but URL is: {inventory_page.page.url}"


@then(parsers.parse('I should see the page title "{expected_title}"'))
def verify_page_title(inventory_page: InventoryPage, expected_title: str):
    """
    Verifies the page title text on the inventory page.
    """
    actual = inventory_page.get_page_title_text()
    assert actual == expected_title, \
        f"Expected title '{expected_title}', but got '{actual}'"


@then("the burger menu icon should be visible")
def verify_burger_menu_icon_visible(inventory_page: InventoryPage):
    """
    Verifies that the burger menu icon is visible on the inventory page.
    """
    assert inventory_page.is_burger_menu_button_visible(), \
        "Expected burger menu icon to be visible, but it was not."


@then("the navigation menu should be open")
def verify_navigation_menu_open(inventory_page: InventoryPage):
    """
    Verifies that the navigation menu is open by checking if the Logout link is visible.
    """
    assert inventory_page.is_logout_link_visible(), \
        "Expected navigation menu to be open (Logout link visible), but it was not."


# CRITICAL FIX: Add decorator for "Then the "Logout" link should be visible in the navigation menu"
@then('the "Logout" link should be visible in the navigation menu')
def verify_logout_link_visible_in_navigation_menu(inventory_page: InventoryPage):
    """
    Verifies that the 'Logout' link is visible in the navigation menu.
    """
    assert inventory_page.is_logout_link_visible(), \
        "Expected 'Logout' link to be visible in the navigation menu, but it was not."


@then(parsers.parse('I should see the "{link_text}" link in the menu'))
def verify_menu_link_visible(inventory_page: InventoryPage, link_text: str):
    """
    Verifies that a specific link is visible within the opened burger menu.
    Currently only supports 'Logout'.
    """
    if link_text == "Logout":
        assert inventory_page.is_logout_link_visible(), \
            f"Expected '{link_text}' link to be visible in the menu, but it was not."
    else:
        pytest.fail(f"Unsupported menu link for visibility check: {link_text}. Only 'Logout' is implemented.")


@then("I should be redirected to the login page")
def verify_redirect_to_login_page(login_page: LoginPage, base_url: str):
    """
    Verifies that the current URL matches the base URL (login page).
    """
    assert login_page.page.url == base_url, \
        f"Expected to be redirected to login page ({base_url}), but current URL is: {login_page.page.url}"


@then(parsers.parse('I should see the error message "{expected_message}"'))
def verify_error_message(login_page: LoginPage, expected_message: str):
    """
    Verifies that a specific error message is displayed on the login page.
    """
    actual = login_page.get_error_message()
    assert actual == expected_message, \
        f"Expected error message '{expected_message}', but got '{actual}'"


# CRITICAL FIX: Add decorator for "Then the login form fields should be visible"
@then("the login form fields should be visible")
def verify_login_form_fields_visible(login_page: LoginPage):
    """
    Verifies that the username and password input fields are visible on the login page.
    """
    assert login_page.is_visible(login_page.USERNAME_INPUT), \
        "Expected username input field to be visible, but it was not."
    assert login_page.is_visible(login_page.PASSWORD_INPUT), \
        "Expected password input field to be visible, but it was not."


@then("the login form should be visible")
def verify_login_form_visible(login_page: LoginPage):
    """
    Verifies that the username, password input fields, and login button are visible
    on the login page, indicating the login form is present and ready for input.
    """
    assert login_page.is_visible(login_page.USERNAME_INPUT), \
        "Expected username input field to be visible, but it was not."
    assert login_page.is_visible(login_page.PASSWORD_INPUT), \
        "Expected password input field to be visible, but it was not."
    assert login_page.is_visible(login_page.LOGIN_BUTTON), \
        "Expected login button to be visible, but it was not."
