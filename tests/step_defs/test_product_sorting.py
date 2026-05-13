"""
Step definitions for features/product_sorting.feature.
Each @given/@when/@then maps an English line to a Python action.
"""
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

@given(parsers.parse('I am logged in as the "{user_type}"'))
def logged_in_user(login_page: LoginPage, inventory_page: InventoryPage, base_url: str, user_type: str):
    """A composite step to log in and land on the inventory page."""
    login_page.open(base_url)
    # This step assumes a login_as method exists on LoginPage as per reference
    # and that all test users share the same password.
    login_page.login_as(user_type, "secret_sauce")
    assert inventory_page.is_loaded(), f"Failed to load inventory page after logging in as {user_type}."


# === WHEN steps ===

@when(parsers.parse('I sort the products by "{sort_option}"'))
def sort_products_by(inventory_page: InventoryPage, sort_option: str):
    inventory_page.select_sort_option(sort_option)


@when("I navigate to the cart page")
def navigate_to_cart(inventory_page: InventoryPage):
    # The InventoryPage POM provided does not have a 'go_to_cart' method.
    # To adhere to the strict list of available methods, we must interact
    # with the page object's 'page' attribute directly.
    # In a real-world scenario, this method would be added to InventoryPage.
    inventory_page.page.click("[data-test='shopping-cart-link']")


@when("I navigate back to the inventory page")
def navigate_back_to_inventory(cart_page: CartPage):
    cart_page.continue_shopping()


# === THEN steps ===

@then("I should be on the inventory page")
def verify_inventory_page(inventory_page: InventoryPage):
    assert inventory_page.is_loaded(), \
        f"Expected to be on inventory page, but URL is: {inventory_page.page.url}"


@then(parsers.parse('the sort dropdown should show "{expected_option}"'))
def verify_active_sort_option(inventory_page: InventoryPage, expected_option: str):
    actual_option = inventory_page.get_active_sort_option()
    assert actual_option == expected_option, \
        f"Expected sort option to be '{expected_option}', but got '{actual_option}'"


@then(parsers.parse('the products should be sorted by "{field}" in "{direction}" order'))
def verify_product_sort_order(inventory_page: InventoryPage, field: str, direction: str):
    is_descending = direction.lower() == 'descending'

    if field.lower() == 'name':
        actual_items = inventory_page.get_product_names()
        expected_items = sorted(actual_items, reverse=is_descending)
        error_message = f"Products are not sorted by name in {direction} order."
    elif field.lower() == 'price':
        actual_items = inventory_page.get_product_prices()
        # Assumes get_product_prices returns a list of numbers (e.g., floats)
        expected_items = sorted(actual_items, reverse=is_descending)
        error_message = f"Products are not sorted by price in {direction} order."
    else:
        raise ValueError(f"Unsupported sort field provided: '{field}'")

    assert actual_items == expected_items, \
        f"{error_message}\nActual:   {actual_items}\nExpected: {expected_items}"
