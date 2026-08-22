"""Step definitions for features/cart_management.feature.

Cart lifecycle: add, add-again (quantity bump), remove, empty, and
persistence across reload / navigation. Steps drive the browser through
page-object methods only — no selectors here.

The cart is server-side state tied to the signed-in account and persists
across runs (inventory: cart.persistent_state). So the empty-cart
assertion here is RELATIVE: the scenario removes exactly the two products
it added and then asserts each of those rows is gone, which holds
whatever the account started with. It does not assert an absolute empty
cart.
"""
from pytest_bdd import given, when, then, parsers, scenarios

from config.paths import feature_path

scenarios(str(feature_path("cart_management")))


# ─────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────

@given("I am on the products page")
def open_products_page(products_page, base_url):
    products_page.open_listing(base_url)
    assert products_page.is_loaded(), "Products listing did not load"


# ─────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────

@when(parsers.re(r'I open the product "(?P<product_name>[^"]*)" from the listing'))
def open_product_from_listing(products_page, product_name):
    products_page.open_product(product_name)


@when("I add the product to the cart")
def add_product_to_cart(product_detail_page):
    product_detail_page.add_to_cart()


@when("I view the cart from the product modal")
def view_cart_from_modal(product_detail_page):
    product_detail_page.go_to_cart_from_modal()


@when("I continue shopping from the product modal")
def continue_shopping_from_modal(product_detail_page):
    product_detail_page.continue_shopping()


@when(parsers.re(r'I remove the product "(?P<product_name>[^"]*)" from the cart'))
def remove_product_from_cart(cart_page, product_name):
    cart_page.remove_product(product_name)


@when("I reload the cart page")
def reload_the_cart_page(cart_page):
    cart_page.reload_cart()


@when("I navigate away to the products page and back to the cart")
def navigate_away_and_back(products_page, cart_page, base_url):
    products_page.open_listing(base_url)
    assert products_page.is_loaded(), "Products listing did not load"
    cart_page.open_cart(base_url)


# ─────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────

@then(parsers.parse("the cart should contain exactly {count:d} product"))
def assert_cart_has_one_product(cart_page, count):
    cart_page.assert_row_count(count)


@then(parsers.parse("the cart should contain exactly {count:d} products"))
def assert_cart_has_n_products(cart_page, count):
    cart_page.assert_row_count(count)


@then(parsers.re(r'the cart should contain the product "(?P<product_name>[^"]*)"'))
def assert_cart_contains_product(cart_page, product_name):
    cart_page.wait_for_product(product_name, present=True)


@then("the cart should be empty")
def assert_cart_empty(cart_page):
    # RELATIVE assertion — the cart is persistent state on a shared account,
    # so an absolute "cart is empty" could be tripped by leftovers from a
    # previous run. Assert instead that the two products THIS scenario added
    # are gone, which is true whatever the account started with.
    cart_page.wait_for_product("Blue Top", present=False)
    cart_page.wait_for_product("Men Tshirt", present=False)


@then(parsers.re(r'the cart row for "(?P<product_name>[^"]*)" should show quantity "(?P<quantity>[^"]*)"'))
def assert_cart_row_quantity(cart_page, product_name, quantity):
    cart_page.wait_for_product(product_name, present=True)
    row = cart_page.row_text(product_name)
    assert quantity in row, f"Expected quantity {quantity!r} in row {row!r}"
