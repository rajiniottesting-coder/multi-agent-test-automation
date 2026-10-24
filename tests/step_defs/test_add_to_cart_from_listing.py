"""Step definitions for features/add_to_cart_from_listing.feature.

Binds the add-to-cart-from-listing scenario to the products and cart page
objects. Interacts with the UI exclusively through page-object methods — no
selectors here. Presence is asserted with waiting readers; the cart quantity
is read through a cell-scoped reader so the assertion matches the value the
sentence names.
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


# ─────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────

@when(parsers.parse('I add the product "{product_name}" to the cart from its listing card'))
def add_product_from_card(products_page, product_name):
    products_page.add_product_to_cart(product_name)


@when("I view the cart from the confirmation modal")
def view_cart_from_modal(products_page):
    products_page.view_cart_from_modal()


# ─────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────

@then("I should remain on the products listing page")
def assert_still_on_listing(products_page):
    assert products_page.is_full_listing_shown(), "Expected to stay on the products listing page"


@then("I should see the added-to-cart confirmation modal")
def assert_added_modal(products_page):
    assert products_page.is_added_modal_shown(), "Expected the added-to-cart confirmation modal"


@then("I should be taken to the cart page")
def assert_on_cart_page(cart_page):
    assert cart_page.is_loaded(), "Expected to be on the cart page"


@then(parsers.parse('the cart should contain the product "{product_name}"'))
def assert_cart_contains(cart_page, product_name):
    cart_page.wait_for_product_present(product_name)


@then(parsers.parse('the cart row for "{product_name}" should show quantity {quantity:d}'))
def assert_cart_quantity(cart_page, product_name, quantity):
    actual = cart_page.quantity_for(product_name)
    assert actual == quantity, (
        f"Expected quantity {quantity} for {product_name!r}, got {actual}"
    )
