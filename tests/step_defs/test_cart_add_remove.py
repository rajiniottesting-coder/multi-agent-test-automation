"""Step definitions for features/cart_add_remove.feature.

Binds the cart add/remove scenarios to page-object methods only. No selectors
live here — every UI interaction goes through ProductsPage, ProductDetailPage
or CartPage. Presence is asserted with waiting readers; absence and empty-state
with non-waiting predicates.
"""
from pytest_bdd import given, when, then, parsers, scenarios

from config.paths import feature_path

scenarios(str(feature_path("cart_add_remove")))


# ─────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────

@given("I have an empty cart")
def start_with_empty_cart(cart_page, base_url):
    """A fresh browser session with no cart activity starts empty."""
    cart_page.open_cart(base_url)


# ─────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────

@when(parsers.parse('I add the product "{product_name}" to the cart and continue shopping'))
def add_product_continue_shopping(products_page, product_detail_page, base_url, product_name):
    products_page.open_listing(base_url)
    products_page.open_product(product_name)
    product_detail_page.add_to_cart()
    product_detail_page.continue_shopping()


@when(parsers.parse('I add the product "{product_name}" to the cart and view the cart'))
def add_product_view_cart(products_page, product_detail_page, base_url, product_name):
    products_page.open_listing(base_url)
    products_page.open_product(product_name)
    product_detail_page.add_to_cart()
    product_detail_page.view_cart_from_modal()


@when(parsers.parse('I remove the product "{product_name}" from the cart'))
def remove_product(cart_page, product_name):
    cart_page.remove_product(product_name)


@when("I view the cart")
def view_cart(cart_page, base_url):
    cart_page.open_cart(base_url)


# ─────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────

@then(parsers.parse("the cart should contain {count:d} products"))
def assert_cart_product_count_plural(cart_page, count):
    actual = cart_page.get_row_count()
    assert actual == count, f"Expected {count} products in cart, found {actual}"


@then(parsers.parse("the cart should contain {count:d} product"))
def assert_cart_product_count_singular(cart_page, count):
    actual = cart_page.get_row_count()
    assert actual == count, f"Expected {count} product in cart, found {actual}"


@then(parsers.parse('the cart should contain the product "{product_name}"'))
def assert_cart_contains_product(cart_page, product_name):
    assert cart_page.has_product(product_name), (
        f"Expected {product_name!r} in cart, got {cart_page.get_product_names()!r}"
    )


@then(parsers.parse('the cart should not contain the product "{product_name}"'))
def assert_cart_missing_product(cart_page, product_name):
    assert not cart_page.has_product(product_name), (
        f"Did not expect {product_name!r} in cart, got {cart_page.get_product_names()!r}"
    )


@then("the cart should be empty")
def assert_cart_empty(cart_page):
    assert cart_page.is_empty(), "Expected the cart to be empty"
