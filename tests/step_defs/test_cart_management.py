"""Step definitions for features/cart_management.feature.

Binds cart-management Gherkin steps to page-object methods only. No selectors
here — every UI interaction goes through ProductsPage, ProductDetailPage or
CartPage.

The cart page is persistent_state (stored against the signed-in session and
surviving the run), so this file asserts RELATIVELY: it checks that a product
this scenario ADDED is present, or that one it REMOVED is gone, using the
waiting row readers. Emptiness is asserted only for products the scenario owns
via wait_for_product(present=False), never by an absolute count/empty check
that a previous run's leftovers could break.
"""
from pytest_bdd import given, when, then, parsers, scenarios

from config.paths import feature_path

scenarios(str(feature_path("cart_management")))


# ─────────────────────────────────────────────────────────────
# Given / When — landing on the products page
# ─────────────────────────────────────────────────────────────

@given("I am on the products page")
@when("I am on the products page")
def open_products_page(products_page, base_url):
    products_page.open_listing(base_url)


# ─────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────

@when(parsers.re(r'I open the product detail page for "(?P<product_name>[^"]*)"'))
def open_product_detail(products_page, product_name):
    products_page.open_product(product_name)


@when("I add the product to the cart")
def add_product_to_cart(product_detail_page):
    product_detail_page.add_to_cart()


@when("I view the cart from the modal")
def view_cart_from_modal(product_detail_page):
    product_detail_page.go_to_cart_from_modal()


@when("I continue shopping from the modal")
def continue_shopping_from_modal(product_detail_page):
    product_detail_page.continue_shopping()


@when(parsers.re(r'I remove "(?P<product_name>[^"]*)" from the cart'))
def remove_product_from_cart(cart_page, product_name):
    cart_page.remove_product(product_name)


@when("I reload the cart page")
def reload_cart_page(cart_page):
    cart_page.reload_cart()


@when("I return to the cart via the navigation")
def return_to_cart_via_nav(cart_page, base_url):
    cart_page.open_cart(base_url)


# ─────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────

@then("the cart should show exactly 1 product")
def assert_cart_has_one_product(cart_page):
    # RELATIVE: the cart is persistent_state, so an absolute row count would
    # also count leftovers from a prior run. Presence of the product this
    # scenario added is what the test actually cares about.
    cart_page.wait_for_product("Blue Top", present=True)


@then("the cart should show exactly 2 products")
def assert_cart_has_two_products(cart_page):
    # RELATIVE: assert both products this scenario added are present, rather
    # than an absolute count that a previous run's leftovers could inflate.
    cart_page.wait_for_product("Blue Top", present=True)
    cart_page.wait_for_product("Men Tshirt", present=True)


@then(parsers.re(r'the cart should contain "(?P<product_name>[^"]*)"'))
def assert_cart_contains(cart_page, product_name):
    cart_page.wait_for_product(product_name, present=True)


@then("the cart should be empty")
def assert_cart_empty(cart_page):
    # RELATIVE emptiness: assert the products this scenario added are gone,
    # which holds whatever the cart started with. An absolute empty-state
    # assertion would fail on leftovers the persistent cart may still hold.
    cart_page.wait_for_product("Blue Top", present=False)
    cart_page.wait_for_product("Men Tshirt", present=False)


@then(parsers.re(r'the quantity for "(?P<product_name>[^"]*)" should be "(?P<quantity>[^"]*)"'))
def assert_product_quantity(cart_page, product_name, quantity):
    row_text = cart_page.row_text_for(product_name)
    assert quantity in row_text, (
        f"Expected quantity {quantity!r} in the {product_name!r} row, got {row_text!r}"
    )
