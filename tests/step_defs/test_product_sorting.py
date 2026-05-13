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


# === Constants ===
# These selectors are defined in the page inventory but not exposed via a method.
# We define them here to avoid magic strings in the step definition, keeping
# with the spirit of POM.
SHOPPING_CART_LINK = "[data-test='shopping-cart-link']"
SORT_DROPDOWN_ACTIVE_OPTION = "[data-test='product-sort-container'] .active_option"


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

@given(parsers.parse('I am logged in as a "{user_type}"'))
def logged_in_user(login_page, inventory_page, base_url, user_type):
    """Logs in as the specified user type."""
    login_page.open(base_url)
    # For all test users on SauceDemo, the password is the same.
    login_page.login_as(user_type, "secret_sauce")
    assert inventory_page.is_loaded(), f"Failed to log in as '{user_type}' or redirect to inventory page."


# === WHEN steps ===

@when(parsers.parse('I sort the products by "{option_text}"'))
def sort_products_by(inventory_page, option_text):
    """Selects a sort option from the dropdown."""
    inventory_page.select_sort_option(option_text)


@when("I navigate to the cart page")
def navigate_to_cart(inventory_page, cart_page):
    """Clicks the shopping cart icon to go to the cart page."""
    inventory_page.page.click(SHOPPING_CART_LINK)
    assert cart_page.is_loaded(), "Did not navigate to the cart page."


@when("I navigate back to the inventory page")
def navigate_back_to_inventory(cart_page, inventory_page):
    """Clicks 'Continue Shopping' to return to the inventory."""
    cart_page.continue_shopping()
    assert inventory_page.is_loaded(), "Did not navigate back to the inventory page."


# === THEN steps ===

@then(parsers.parse('the product sort dropdown should show "{expected_text}"'))
def verify_sort_dropdown_text(inventory_page, expected_text):
    """Verifies the text of the currently active sort option."""
    actual_text = inventory_page.page.locator(SORT_DROPDOWN_ACTIVE_OPTION).inner_text()
    assert actual_text == expected_text, \
        f"Expected sort option to be '{expected_text}', but it was '{actual_text}'."


@then(parsers.parse('the products should be sorted by "{sort_key}" in "{sort_direction}" order'))
def verify_product_sort_order(inventory_page, sort_key, sort_direction):
    """Verifies that the products are sorted correctly based on name or price."""
    is_descending = sort_direction == "descending"

    if sort_key == "name":
        actual_items = inventory_page.get_product_names()
        # Sort is case-sensitive, which is correct for this app
        expected_items = sorted(actual_items, reverse=is_descending)
    elif sort_key == "price":
        price_strings = inventory_page.get_product_prices()
        # Convert price strings like '$29.99' to float for sorting
        actual_items = [float(p.replace('$', '')) for p in price_strings]
        expected_items = sorted(actual_items, reverse=is_descending)
    else:
        pytest.fail(f"Unknown sort key provided: '{sort_key}'. Must be 'name' or 'price'.")

    assert actual_items == expected_items, \
        f"Products not sorted by '{sort_key}' in '{sort_direction}' order.\n" \
        f"Expected: {expected_items}\n" \
        f"Actual:   {actual_items}"
