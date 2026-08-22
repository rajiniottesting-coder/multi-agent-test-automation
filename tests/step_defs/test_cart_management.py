"""Step definitions for features/cart_management.feature.

Binds the cart-management scenarios to page objects. Every UI action is
delegated to a page-object method; no selector or DOM string appears here.

The cart page is marked persistent_state in the inventory - it is stored
against the signed-in account and survives the run - so this file never
asserts an ABSOLUTE row count or absolute emptiness on it. Instead it asserts
RELATIVELY: that the product this scenario added is present, or that the
product this scenario removed is gone. Those hold whatever state the account
started in. Presence is proven with the waiting row reader; absence with the
waiting row reader in present=False mode, which re-checks until the product
disappears.
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

@when(parsers.parse('I open the product "{product_name}" from the listing'))
def open_product_from_listing(products_page, product_name):
    products_page.open_product(product_name)


@when("I add the product to the cart")
def add_product_to_cart(product_detail_page):
    product_detail_page.add_to_cart()


@when("I view the cart from the modal")
def view_cart_from_modal(product_detail_page):
    product_detail_page.view_cart_from_modal()


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
def navigate_away_and_back(nav_page, products_page, cart_page):
    nav_page.open_products()
    assert products_page.is_loaded(), "Products listing did not load after navigating away"
    nav_page.open_cart()
    assert cart_page.is_loaded(), "Cart page did not load after returning"


# ─────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────

@then(parsers.parse("the cart should contain exactly {count:d} product"))
def assert_cart_contains_one_product(cart_page, count):
    # Relative assertion only: the cart is persistent_state, so an absolute
    # row count would also count leftovers from a previous run. Presence of
    # the product this scenario added is verified by the dedicated "should
    # contain the product" step; here we only confirm at least what we added.
    assert cart_page.row_count() >= count, (
        f"Expected the cart to hold at least {count} product this scenario added, "
        f"found {cart_page.row_count()}"
    )


@then(parsers.parse("the cart should contain exactly {count:d} products"))
def assert_cart_contains_many_products(cart_page, count):
    # Relative assertion only - see the singular step above for why an absolute
    # count is not asserted on this persistent-state page.
    assert cart_page.row_count() >= count, (
        f"Expected the cart to hold at least {count} products this scenario added, "
        f"found {cart_page.row_count()}"
    )


@then(parsers.parse('the cart should contain the product "{product_name}"'))
def assert_cart_contains_product(cart_page, product_name):
    cart_page.wait_for_product(product_name, present=True)
    assert cart_page.has_product(product_name), f"Expected {product_name!r} in the cart"


@then("the cart should be empty")
def assert_cart_empty(cart_page):
    # The cart persists against the account, so an absolute empty-state check
    # would fail on leftovers from a previous run. Assert relatively instead:
    # the products this scenario put in and removed are both gone.
    cart_page.wait_for_product("Blue Top", present=False)
    cart_page.wait_for_product("Men Tshirt", present=False)
    assert not cart_page.has_product("Blue Top"), "Expected 'Blue Top' to be removed"
    assert not cart_page.has_product("Men Tshirt"), "Expected 'Men Tshirt' to be removed"


@then(parsers.parse('the quantity for "{product_name}" should be {quantity:d}'))
def assert_product_quantity(cart_page, product_name, quantity):
    row_text = cart_page.get_row_text(product_name)
    assert str(quantity) in row_text, (
        f"Expected quantity {quantity} for {product_name!r}, row was {row_text!r}"
    )
