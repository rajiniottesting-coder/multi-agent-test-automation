"""Step definitions for features/cart_management.feature.

Binds cart-management Gherkin steps to page-object methods. Step defs call
named page-object methods only; no selectors, waits, or DOM access here.

PERSISTENT STATE — the cart page ('cart') is declared persistent_state: the
application stores it against the signed-in session/account, so it survives
logout and survives the run. A previous run's leftovers would be counted by any
ABSOLUTE row-count or emptiness assertion.

To make absolute assertions legitimate, the scenario OWNS its starting state
via the "I start with an empty cart" Given, which opens the cart and removes
EVERY leftover row before the scenario proceeds. Because the cart is emptied
first, every item present downstream was put there by this scenario itself — so
exact row-count, quantity, and emptiness assertions describe state this test
owns rather than inherited leftovers. That ownership is what removes the
persistent-state hazard: the Given establishes a genuinely empty baseline, so
the later exact assertions are safe.
"""
from pytest_bdd import given, when, then, parsers, scenarios

from config.paths import feature_path

scenarios(str(feature_path("cart_management")))


# ─────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────

@given("I start with an empty cart")
def start_with_empty_cart(cart_page, base_url) -> None:
    """Own the starting state: open the cart and remove any leftover rows.

    The cart is persistent server-side state, so a previous run may have left
    items behind. Clearing them here makes 'empty' and exact-count assertions
    downstream describe state this scenario owns, not inherited leftovers.
    """
    cart_page.open_cart(base_url)
    for name in cart_page.product_names():
        cart_page.remove_product(name)
    assert cart_page.is_empty(), (
        "Cart was not emptied before the scenario; leftover state remains"
    )


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
    product_detail_page.continue_shopping()


@when(parsers.parse('I remove the product "{product_name}" from the cart'))
def remove_product(cart_page, product_name) -> None:
    cart_page.remove_product(product_name)


@when("I reload the cart page")
def reload_cart_page(cart_page) -> None:
    cart_page.reload_cart()


@when("I return to the cart from the navigation")
def return_to_cart(cart_page, base_url) -> None:
    cart_page.open_cart(base_url)


# ─────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────

@then(parsers.parse("the cart should contain exactly {count:d} product"))
def assert_cart_one_product(cart_page, count) -> None:
    # Absolute count is legitimate: the "I start with an empty cart" Given
    # emptied the cart first, so every row present was added by this scenario.
    cart_page.assert_row_count(count)


@then(parsers.parse("the cart should contain exactly {count:d} products"))
def assert_cart_products(cart_page, count) -> None:
    # Absolute count is legitimate: the scenario owns its starting state via
    # the empty-cart Given, so leftovers cannot inflate the count.
    cart_page.assert_row_count(count)


@then(parsers.parse('the cart should contain the product "{product_name}"'))
def assert_cart_contains(cart_page, product_name) -> None:
    assert cart_page.contains_product(product_name), (
        f"Expected {product_name!r} in cart, found {cart_page.product_names()!r}"
    )


@then("the cart should be empty")
def assert_cart_empty(cart_page) -> None:
    # Absolute emptiness is legitimate: the scenario owns its starting state
    # via the empty-cart Given, so no leftover rows can be counted here.
    assert cart_page.is_empty(), "Expected the cart to be empty"


@then(parsers.parse('the quantity for "{product_name}" should be {quantity:d}'))
def assert_quantity(cart_page, product_name, quantity) -> None:
    actual = cart_page.get_quantity(product_name)
    assert actual == quantity, (
        f"Expected quantity {quantity} for {product_name!r}, got {actual}"
    )


@then(parsers.parse('the total for "{product_name}" should be "{expected_total}"'))
def assert_total(cart_page, product_name, expected_total) -> None:
    actual = cart_page.get_total_price(product_name)
    assert expected_total in actual, (
        f"Expected total {expected_total!r} for {product_name!r}, got {actual!r}"
    )
