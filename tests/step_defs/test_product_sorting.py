"""
Step definitions for features/product-sorting.feature.
Each @given/@when/@then maps an English line to a Python action.
"""
from pathlib import Path

import pytest
from pytest_bdd import scenarios, given, when, then, parsers

from pages.login_page import LoginPage
from pages.inventory_page import InventoryPage
from pages.cart_page import CartPage
from config.paths import feature_path


# Bind this test module to the feature file
scenarios(str(feature_path("product_sorting")))


# === Page Object fixtures (created per-test) ===

@pytest.fixture
def login_page(page):
    return LoginPage(page)


@pytest.fixture
def inventory_page(page):
    return InventoryPage(page)


@pytest.fixture
def cart_page(page):
    return CartPage(page)


# === GIVEN steps ===

@given("I am on the SauceDemo login page")
def open_login_page(login_page, base_url):
    """Navigates to the login page."""
    login_page.open(base_url)


@given(parsers.parse('I am logged in as a "{user_type}"'))
def logged_in_user(login_page, inventory_page, base_url, user_type):
    """Logs in as a specified user and ensures the inventory page is loaded."""
    password = "secret_sauce"  # All test users share the same password
    login_page.open(base_url)
    login_page.login_as(user_type, password)
    assert inventory_page.is_loaded(), "Failed to load inventory page after login."


# === WHEN steps ===

@when(parsers.parse('I log in with username "{username}" and password "{password}"'))
def login_with_credentials(login_page, username, password):
    """Enters credentials and clicks login."""
    login_page.login_as(username, password)


@when(parsers.parse('I sort the products by "{option_text}"'))
def sort_products(inventory_page, option_text):
    """Selects a sort option from the dropdown."""
    inventory_page.sort_products_by(option_text)


@when("I navigate to the cart page")
def go_to_cart(inventory_page):
    """Clicks the shopping cart icon."""
    inventory_page.click_shopping_cart()


@when("I navigate back to the inventory page")
def go_back_to_inventory(cart_page):
    """Clicks the 'Continue Shopping' button from the cart."""
    cart_page.continue_shopping()


# === THEN steps ===

@then("I should be on the inventory page")
def verify_inventory_page(inventory_page):
    """Asserts that the current page is the inventory page."""
    assert inventory_page.is_loaded(), \
        f"Expected inventory page, but URL is: {inventory_page.page.url}"


@then(parsers.parse('the product sort dropdown should show "{expected_option}"'))
def verify_active_sort_option(inventory_page, expected_option):
    """Asserts that the correct sort option is displayed as active."""
    actual_option = inventory_page.get_active_sort_option_text()
    assert actual_option == expected_option, \
        f"Expected sort option '{expected_option}', but got '{actual_option}'"


@then(parsers.parse('the products should be sorted by {sort_key} in {sort_order} order'))
def verify_product_sort_order(inventory_page, sort_key, sort_order):
    """
    Asserts that the products are sorted correctly based on the key and order.
    sort_key: 'name' or 'price'
    sort_order: 'ascending' or 'descending'
    """
    is_descending = (sort_order.lower() == "descending")

    if sort_key == "name":
        actual_items = inventory_page.get_product_names()
    elif sort_key == "price":
        actual_items = inventory_page.get_product_prices()
    else:
        pytest.fail(f"Unsupported sort key provided: '{sort_key}'")

    # The page object methods get_product_names() and get_product_prices()
    # are expected to return lists of strings and floats, respectively.
    expected_items = sorted(actual_items, reverse=is_descending)
    assert actual_items == expected_items, \
        f"Products are not sorted by {sort_key} in {sort_order} order."
