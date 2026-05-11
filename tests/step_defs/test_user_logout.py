"""
Step definitions for features/user_logout.feature.
Each @given/@when/@then maps an English line to a Python action.
"""
import pytest
from pytest_bdd import scenarios, given, when, then, parsers

from pages.login_page import LoginPage
from pages.inventory_page import InventoryPage
from config.paths import feature_path


# Bind this test module to the feature file
scenarios(str(feature_path("user_logout")))


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
    login_page.open(base_url)
    login_page.login_as("standard_user", "secret_sauce")
    assert inventory_page.is_loaded(), "Failed to log in or redirect to inventory page."


@given("I am on the inventory page")
def on_inventory_page(inventory_page):
    assert inventory_page.is_loaded(), \
        f"Expected to be on inventory page, but URL is {inventory_page.page.url}"


# === WHEN steps ===

@when("I open the burger menu")
def open_burger_menu(inventory_page):
    inventory_page.open_burger_menu()


@when("I log out")
def log_out(inventory_page):
    inventory_page.logout()


@when("I attempt to navigate directly to the inventory page")
def nav_to_inventory(page, base_url):
    inventory_url = f"{base_url.rstrip('/')}/inventory.html"
    page.goto(inventory_url)


# === THEN steps ===

@then("I should be redirected to the login page")
def verify_on_login_page(page, base_url):
    current_url = page.url.rstrip('/')
    expected_url = base_url.rstrip('/')
    assert current_url == expected_url, \
        f"Expected to be on login page ({expected_url}), but was on {current_url}"


@then("the login form should be visible")
def verify_login_form_visible(login_page):
    assert login_page.is_visible(login_page.USERNAME_INPUT), "Username input not visible"
    assert login_page.is_visible(login_page.PASSWORD_INPUT), "Password input not visible"


@then("the logout link should be visible")
def verify_logout_link_visible(inventory_page):
    # This step assumes InventoryPage exposes a `LOGOUT_LINK` class attribute
    # with the selector, and an `is_visible` method from a base class.
    # This is consistent with the LoginPage implementation pattern.
    assert inventory_page.is_visible(inventory_page.LOGOUT_LINK), \
        "Logout link not visible in burger menu"


@then(parsers.parse('I should see the error message "{expected_message}"'))
def verify_error_message(login_page, expected_message):
    actual = login_page.get_error_message()
    assert actual == expected_message, \
        f"Expected error '{expected_message}', but got '{actual}'"
