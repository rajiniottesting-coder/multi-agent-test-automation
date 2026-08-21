"""Step definitions for features/cart_management.feature.

Binds the cart-management scenarios to the ProductsPage, ProductDetailPage,
CartPage and NavPage page objects. Every step delegates to a page-object
method — no selectors and no raw page.* calls live here.

Starting-state ownership (the cart is persistent_state):
The cart is stored server-side against the signed-in account, so it survives
logout and survives the run — a previous run's leftovers are still there and no
wait removes them. "I start with an empty cart" clears whatever it finds, so
the scenario OWNS its starting point. The absolute-count and empty assertions
that follow therefore reflect ONLY what THIS scenario added or removed, not
inherited rows.
"""
from pytest_bdd import given, when, then, parsers, scenarios

from config.paths import feature_path

scenarios(str(feature_path("cart_management")))


# ─────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────

@given("I start with an empty cart")
def start_with_empty_cart(cart_page, base_url) -> None:
    """Own the starting state: open the cart and remove every leftover row so
    the scenario begins from a genuinely empty cart, regardless of what an
    earlier run left against this account."""
    cart_page.open_cart(base_url)
    for name in list(cart_page.get_product_names()):
        cart_page.remove_product(name)


# ─────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────

@when("I open the products listing")
def open_products_listing(products_page, base_url) -> None:
    products_page.open_listing(base_url)


@when(parsers.parse('I view the product "{product_name}"'))
def view_product(products_page, product_name) -> None:
    products_page.open_product(product_name)


@when("I add the product to the cart")
def add_product_to_cart(product_detail_page) -> None:
    product_detail_page.add_to_cart()


@when("I view the cart from the modal")
def view_cart_from_modal(product_detail_page) -> None:
    product_detail_page.view_cart_from_modal()


@when("I continue shopping from the modal")
def continue_shopping_from_modal(product_detail_page) -> None:
    product_detail_page.continue_shopping_from_modal()


@when(parsers.parse('I remove the product "{product_name}" from the cart'))
def remove_product(cart_page, product_name) -> None:
    cart_page.remove_product(product_name)


@when("I reload the cart page")
def reload_cart_page(cart_page) -> None:
    cart_page.refresh()


@when("I open the cart from the navigation")
def open_cart_from_nav(nav_page, cart_page) -> None:
    nav_page.go_to_cart()
    cart_page.confirm_arrival()


# ─────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────

@then(parsers.parse('the cart should contain exactly {count:d} product'))
def cart_contains_one_product(cart_page, count) -> None:
    cart_page.assert_row_count(count)


@then(parsers.parse('the cart should contain exactly {count:d} products'))
def cart_contains_n_products(cart_page, count) -> None:
    cart_page.assert_row_count(count)


@then(parsers.parse('the cart should contain the product "{product_name}"'))
def cart_contains_product(cart_page, product_name) -> None:
    assert cart_page.has_product(product_name), \
        f"Expected {product_name!r} in the cart"


@then("the cart should be empty")
def cart_should_be_empty(cart_page) -> None:
    """The scenario cleared the cart in its Given and then removed every row it
    added, so it OWNS this empty state — the empty-cart message reflects this
    scenario's own removals, not inherited leftovers."""
    assert cart_page.is_empty(), "Expected the cart to be empty"


@then(parsers.parse('the product "{product_name}" should have quantity "{quantity}"'))
def product_should_have_quantity(cart_page, product_name, quantity) -> None:
    row_text = cart_page.get_row_text(product_name)
    assert quantity in row_text, \
        f"Expected quantity {quantity!r} for {product_name!r}, got row {row_text!r}"
