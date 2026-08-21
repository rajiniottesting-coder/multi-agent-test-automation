"""Step definitions for features/cart_management.feature.

Binds the cart-management scenarios to the ProductsPage, ProductDetailPage,
CartPage and NavPage page objects. Every step interacts with the UI only
through page-object methods — no selectors appear here.

The cart is server-side, per-account and PERSISTENT: it survives logout and
survives the run. A scenario that reuses the shared session inherits whatever
a previous run left behind, so absolute claims ("exactly N rows", "empty")
are only safe when the scenario OWNS its starting state. The "I start with an
empty cart" Given clears any residual items up front, so every row seen
thereafter was added by this scenario — that is what makes the later row-count
and empty assertions true by construction rather than by chance.
"""
from pytest_bdd import given, when, then, parsers, scenarios

from config.paths import feature_path

scenarios(str(feature_path("cart_management")))


# ─────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────

@given("I start with an empty cart")
def start_with_empty_cart(cart_page, base_url):
    """Open the cart and clear any residual items so it begins empty.

    The cart is persistent per-account state, so a previous run may have left
    items behind. Removing everything here makes the scenario own its starting
    state, which is what lets later absolute assertions (row counts, empty)
    hold — every row seen from now on was added by this scenario.
    """
    cart_page.open_cart(base_url)
    for name in list(cart_page.product_names()):
        cart_page.remove_product(name)


# ─────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────

@when("I open the products listing")
def open_products_listing(products_page, base_url):
    products_page.open_listing(base_url)


@when(parsers.parse('I open the product "{product_name}" from the listing'))
def open_product_from_listing(products_page, product_name):
    products_page.open_product(product_name)


@when("I add the product to the cart")
def add_product_to_cart(product_detail_page):
    product_detail_page.add_to_cart()


@when("I view the cart from the product modal")
def view_cart_from_modal(product_detail_page):
    product_detail_page.view_cart_from_modal()


@when("I continue shopping from the product modal")
def continue_shopping_from_modal(product_detail_page):
    product_detail_page.continue_shopping()


@when(parsers.parse('I remove the product "{product_name}" from the cart'))
def remove_product_from_cart(cart_page, product_name):
    cart_page.remove_product(product_name)


@when("I reload the cart page")
def reload_cart_page(cart_page):
    cart_page.reload_cart()


@when("I open the cart from the navigation")
def open_cart_from_navigation(nav_page):
    nav_page.open_cart()


# ─────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────

@then(parsers.parse("the cart should contain exactly {count:d} row"))
def assert_cart_row_count_singular(cart_page, count):
    cart_page.assert_row_count(count)


@then(parsers.parse("the cart should contain exactly {count:d} rows"))
def assert_cart_row_count_plural(cart_page, count):
    cart_page.assert_row_count(count)


@then(parsers.parse('the cart should contain the product "{product_name}"'))
def assert_cart_contains_product(cart_page, product_name):
    cart_page.wait_for_product(product_name, present=True)


@then("the cart should be empty")
def assert_cart_empty(cart_page):
    """The scenario cleared its starting state in the Given and then removed
    every product it added, so each product the scenario touched is confirmed
    gone before the empty-state is asserted. This is a relative claim about
    what this scenario owns, which holds whatever the account started with.
    """
    cart_page.wait_for_product("Blue Top", present=False)
    cart_page.wait_for_product("Men Tshirt", present=False)
    assert cart_page.is_empty(), "Expected the cart to be empty"


@then(parsers.parse('the "{product_name}" row should show quantity "{quantity}"'))
def assert_row_quantity(cart_page, product_name, quantity):
    cart_page.wait_for_product(product_name, present=True)
    row_text = cart_page.get_product_row_text(product_name)
    assert quantity in row_text, (
        f"Expected quantity {quantity!r} in {product_name!r} row, got {row_text!r}"
    )
