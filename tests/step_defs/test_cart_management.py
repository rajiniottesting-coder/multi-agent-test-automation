"""Step definitions for features/cart_management.feature.

Binds cart-management scenarios to page-object methods only. No selectors,
no raw self.page.* calls, no assertions on multi-match families.

Fixtures (products_page, product_detail_page, cart_page) come from
tests/step_defs/conftest.py and resolve hierarchically.
"""
from pytest_bdd import given, when, then, parsers, scenarios

from config.paths import feature_path

scenarios(str(feature_path("cart_management")))


# ─────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────

@given("I have an empty cart")
def start_with_empty_cart(cart_page, base_url):
    """Fresh session — navigate to the cart to establish a known start state."""
    cart_page.open_cart(base_url)


# ─────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────

@when("I open the product listing")
def open_product_listing(products_page, base_url):
    products_page.open_listing(base_url)


@when(parsers.parse('I open the product "{product_name}" from the listing'))
def open_product_from_listing(products_page, product_name):
    products_page.open_product(product_name)


@when("I add the product to the cart")
def add_product_to_cart(product_detail_page):
    product_detail_page.add_product_to_cart()


@when("I continue shopping")
def continue_shopping(product_detail_page):
    product_detail_page.continue_shopping()


@when("I view the cart from the modal")
def view_cart_from_modal(product_detail_page):
    product_detail_page.view_cart()


@when("I view the cart")
def view_the_cart(cart_page, base_url):
    cart_page.open_cart(base_url)


@when(parsers.parse('I remove the product "{product_name}" from the cart'))
def remove_product_from_cart(cart_page, product_name):
    cart_page.remove_product(product_name)


# ─────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────

@then("the cart should be empty")
def assert_cart_empty(cart_page):
    assert cart_page.is_empty(), "Expected the cart to be empty"


@then(parsers.parse("the cart should contain {count:d} products"))
def assert_cart_contains_products(cart_page, count):
    actual = cart_page.get_row_count()
    assert actual == count, f"Expected {count} products in the cart, found {actual}"


@then(parsers.parse("the cart should contain {count:d} product"))
def assert_cart_contains_product_singular(cart_page, count):
    actual = cart_page.get_row_count()
    assert actual == count, f"Expected {count} product in the cart, found {actual}"


@then(parsers.parse('the cart should contain the product "{product_name}"'))
def assert_cart_has_product(cart_page, product_name):
    assert cart_page.has_product(product_name), \
        f"Expected {product_name!r} to be in the cart"


@then(parsers.parse('the cart should not contain the product "{product_name}"'))
def assert_cart_missing_product(cart_page, product_name):
    assert not cart_page.has_product(product_name), \
        f"Expected {product_name!r} to be absent from the cart"
