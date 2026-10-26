"""Step definitions for features/add_to_cart_from_listing.feature.

Binds the add-to-cart-from-listing scenario to the products and cart page
objects. Every step the feature uses is declared here, because pytest-bdd
steps are module-scoped and do not resolve across step-def modules.

The cart assertion reuses the sentence committed in test_cart_management.py and
asserts EXACTLY what that definition asserts.
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

@when(parsers.parse('I add "{product_name}" to the cart from its product card'))
def add_product_from_card(products_page, product_name):
    products_page.add_product_to_cart(product_name)


@when("I view the cart from the confirmation modal")
def view_cart_from_modal(products_page):
    products_page.view_cart_from_modal()


# ─────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────

@then("I should see the product-added confirmation modal")
def assert_added_modal(products_page):
    assert products_page.has_added_modal(), "Expected the product-added confirmation modal"


@then("I should remain on the products listing page")
def assert_still_on_listing(products_page):
    assert products_page.is_on_listing(), "Expected to remain on the products listing page"


@then("I should be on the cart page")
def assert_on_cart_page(cart_page):
    assert cart_page.is_loaded(), "Expected to be on the cart page"


@then(parsers.parse('the cart should contain "{product_name}" with quantity {quantity:d}'))
def assert_cart_contains_with_quantity(cart_page, product_name, quantity):
    cart_page.wait_for_product(product_name, present=True)
    actual = cart_page.quantity_for(product_name)
    assert actual == quantity, (
        f"Expected {product_name!r} with quantity {quantity}, got {actual}"
    )
