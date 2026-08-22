"""Step definitions for features/cart_management.feature.

All UI mechanics are delegated to page objects. This module declares every
step its own feature file uses, since pytest-bdd steps are module-scoped.
"""
from pytest_bdd import given, when, then, parsers, scenarios

from config.paths import feature_path

scenarios(str(feature_path("cart_management")))


# ─────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────

@given("the cart is empty")
def cart_is_empty(cart_page, base_url):
    """Own the starting state: clear any leftover items so absolute
    row-count and empty-cart assertions are honest."""
    cart_page.open_cart(base_url)
    cart_page.empty_the_cart()


# ─────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────

@when(parsers.parse('I open the "{product_name}" product from the listing'))
def open_product_from_listing(products_page, base_url, product_name):
    products_page.open_listing(base_url)
    products_page.open_product(product_name)


@when("I add the product to the cart")
def add_product_to_cart(product_detail_page):
    product_detail_page.add_to_cart()


@when("I view the cart from the modal")
def view_cart_from_modal(product_detail_page):
    product_detail_page.view_cart()


@when("I continue shopping from the modal")
def continue_shopping_from_modal(product_detail_page):
    product_detail_page.continue_shopping()


@when(parsers.parse('I remove the product "{product_name}" from the cart'))
def remove_product_from_cart(cart_page, product_name):
    cart_page.remove_product(product_name)


@when("I reload the cart page")
def reload_cart_page(cart_page):
    cart_page.reload_cart()


@when("I navigate away to the products page and back to the cart")
def navigate_away_and_back(products_page, cart_page, base_url):
    products_page.open_listing(base_url)
    cart_page.open_cart(base_url)


# ─────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────

@then(parsers.parse('the cart should contain the product "{product_name}"'))
def assert_cart_contains_product(cart_page, product_name):
    cart_page.wait_for_product(product_name, present=True)


@then(parsers.parse("the cart should contain exactly {count:d} row"))
def assert_cart_row_count_singular(cart_page, count):
    cart_page.assert_row_count(count)


@then(parsers.parse("the cart should contain exactly {count:d} rows"))
def assert_cart_row_count_plural(cart_page, count):
    cart_page.assert_row_count(count)


@then(parsers.parse('the product "{product_name}" should no longer be in the cart'))
def assert_product_removed(cart_page, product_name):
    cart_page.wait_for_product(product_name, present=False)


@then("the cart should be empty")
def assert_cart_empty(cart_page):
    assert cart_page.is_empty(), "Expected the cart to be empty"


@then(parsers.parse('the quantity for "{product_name}" should be "{quantity}"'))
def assert_quantity_for_product(cart_page, product_name, quantity):
    actual = cart_page.get_quantity_for(product_name)
    assert actual == quantity, (
        f"Expected quantity {quantity!r} for {product_name!r}, got {actual!r}"
    )
