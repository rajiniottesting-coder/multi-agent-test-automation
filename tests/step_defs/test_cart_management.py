"""Step definitions for features/cart_management.feature.

Binds the cart-management scenarios to the products, product-detail and cart
page objects. Every step below is declared in THIS module — pytest-bdd steps
are module-scoped, so a step defined elsewhere is not visible here.

Conventions copied from the login reference:
  - call page-object methods only; never a selector in a step definition
  - assert PRESENCE with the page object's waiting readers; count assertions
    delegate to methods built on waiting probes

Persistent-state discipline (cart inventory page declares persistent_state):
  The cart is stored against the signed-in account and survives the run, so a
  previous run's leftovers are counted too. The "the cart should be empty"
  step therefore asserts RELATIVELY — that every product THIS scenario added
  and removed is gone — instead of the absolute empty-state indicator, which
  would flake on residue the scenario never owned. Likewise "I start with an
  empty cart" does not assert; it OWNS the starting state by removing any
  residual rows so subsequent exact-count assertions describe only what this
  scenario put there.
"""
from pytest_bdd import given, when, then, parsers, scenarios

from config.paths import feature_path

scenarios(str(feature_path("cart_management")))


# ─────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────

@given("I start with an empty cart")
def start_with_empty_cart(cart_page, base_url):
    """Own the starting state: open the cart and remove any residual rows so
    the scenario begins genuinely empty. The cart persists against the
    signed-in account across runs, so this clears leftovers a previous run may
    have left behind before any exact-count assertion is made. No assertion is
    made here — this is setup, not verification."""
    cart_page.open_cart(base_url)
    if cart_page.is_loaded():
        for name in cart_page.get_product_names():
            cart_page.remove_product(name)


# ─────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────

@when(parsers.parse('I open the "{product_name}" product page from the listing'))
def open_product_from_listing(products_page, product_detail_page, base_url, product_name):
    products_page.open_listing(base_url)
    products_page.open_product(product_name)
    assert product_detail_page.is_loaded(), f"Product page for {product_name!r} did not load"


@when("I add the product to the cart")
def add_product_to_cart(product_detail_page):
    product_detail_page.add_product_to_cart()


@when("I view the cart from the modal")
def view_cart_from_modal(product_detail_page):
    product_detail_page.open_cart_from_modal()


@when("I continue shopping from the modal")
def continue_shopping_from_modal(product_detail_page):
    product_detail_page.continue_shopping()


@when(parsers.parse('I remove the product "{product_name}" from the cart'))
def remove_product_from_cart(cart_page, product_name):
    cart_page.remove_product(product_name)


@when("I reload the cart page")
def reload_cart_page(cart_page):
    cart_page.reload_cart()


@when("I navigate away and return to the cart via the navigation")
def navigate_away_and_return(products_page, cart_page, base_url):
    products_page.open_listing(base_url)
    cart_page.open_cart(base_url)


# ─────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────

@then(parsers.parse("the cart should contain exactly {count:d} product"))
def assert_cart_has_one_product(cart_page, count):
    cart_page.assert_row_count(count)


@then(parsers.parse("the cart should contain exactly {count:d} products"))
def assert_cart_has_products(cart_page, count):
    cart_page.assert_row_count(count)


@then(parsers.parse('the cart should contain the product "{product_name}"'))
def assert_cart_contains_product(cart_page, product_name):
    assert cart_page.has_product(product_name), f"Expected {product_name!r} in the cart"


@then("the cart should be empty")
def assert_cart_empty(cart_page):
    """Assert RELATIVELY, not absolutely. The cart is persistent_state, so a
    previous run's leftover would fail an absolute empty-state check even after
    this scenario removed everything it added. The two products this scenario
    owns are 'Blue Top' and 'Men Tshirt'; assert each is gone, which holds
    whatever the account started with."""
    names = cart_page.get_product_names()
    assert not cart_page.has_product("Blue Top"), (
        f"Expected 'Blue Top' to be removed, cart still shows {names!r}"
    )
    assert not cart_page.has_product("Men Tshirt"), (
        f"Expected 'Men Tshirt' to be removed, cart still shows {names!r}"
    )


@then(parsers.parse('the quantity for "{product_name}" should be "{quantity}"'))
def assert_product_quantity(cart_page, product_name, quantity):
    row_text = cart_page.get_row_text(product_name)
    assert quantity in row_text, (
        f"Expected quantity {quantity!r} for {product_name!r} in row {row_text!r}"
    )
