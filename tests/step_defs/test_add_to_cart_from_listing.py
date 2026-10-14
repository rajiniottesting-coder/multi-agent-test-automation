"""Step definitions for features/add_to_cart_from_listing.feature.

Binds the add-to-cart-from-listing scenario to the ProductsPage and CartPage
page objects. Steps call page-object methods only — no selectors here.
"""
from pytest_bdd import given, when, then, parsers, scenarios

from config.paths import feature_path

scenarios(str(feature_path("add_to_cart_from_listing")))


# ─────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────

@given("I am on the products listing page")
def open_products_listing(products_page, base_url):
    products_page.open_products(base_url)
    assert products_page.is_loaded(), "Products listing page did not load"


# ─────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────

@when(parsers.parse('I add "{product_name}" to the cart from its listing card'))
def add_product_from_card(products_page, product_name):
    products_page.add_to_cart_from_card(product_name)


@when("I view the cart from the confirmation modal")
def view_cart_from_modal(products_page):
    products_page.view_cart_from_modal()


# ─────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────

@then("I should see the product added confirmation modal")
def assert_added_modal(products_page):
    assert products_page.is_added_modal_shown(), "Add-to-cart confirmation modal did not appear"


@then("I should be on the cart page")
def assert_on_cart_page(cart_page):
    assert cart_page.is_loaded(), "Expected to be on the cart page"


@then(parsers.parse('the cart should contain "{product_name}" with quantity {quantity:d}'))
def assert_cart_contains_product_with_quantity(cart_page, product_name, quantity):
    cart_page.wait_for_product(product_name, present=True)
    actual_quantity = cart_page.quantity_for(product_name)
    assert actual_quantity == str(quantity), (
        f"Expected quantity {quantity} for {product_name!r}, got {actual_quantity!r}"
    )
