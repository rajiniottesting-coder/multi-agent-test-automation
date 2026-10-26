"""Step definitions for features/add_to_cart_from_listing.feature.

Binds the SCRUM-259 scenario — adding a product to the cart directly from its
card on the all-products listing — to the ProductsPage and CartPage methods.

Conventions followed from the reference suite:
- Declare every step the feature uses in THIS module; steps are module-scoped.
- Call page-object methods only; no selectors in step definitions.
- Assert PRESENCE with waiting readers; the cart quantity reuses the committed
  definition exactly.
"""
from pytest_bdd import given, when, then, parsers, scenarios

from config.paths import feature_path

scenarios(str(feature_path("add_to_cart_from_listing")))


# ─────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────

@given("I am on the all-products page")
def open_products_page(products_page, base_url):
    products_page.open_products(base_url)


# ─────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────

@when(parsers.parse('I add "{product_name}" to the cart from its product card'))
def add_product_from_card(products_page, product_name):
    products_page.add_product_to_cart(product_name)


@when("I click View Cart in the confirmation modal")
def click_view_cart_in_modal(products_page):
    products_page.open_cart_from_modal()


# ─────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────

@then(parsers.parse('I should see "{product_name}" in the product listing'))
def assert_product_in_listing(products_page, product_name):
    assert products_page.has_product(product_name), (
        f"Expected {product_name!r} in the product listing"
    )


@then("I should see the product added confirmation modal")
def assert_added_modal_shown(products_page):
    assert products_page.is_added_modal_shown(), (
        "Expected the product added confirmation modal"
    )


@then("I should remain on the all-products page")
def assert_remain_on_products(products_page):
    assert products_page.is_full_listing_shown(), (
        "Expected to remain on the all-products listing"
    )


@then("I should be on the cart page")
def assert_on_cart_page(cart_page):
    assert cart_page.is_loaded(), "Expected to be on the cart page"


@then(parsers.parse('the cart should contain "{product_name}" with quantity {quantity:d}'))
def assert_cart_contains_with_quantity(cart_page, product_name, quantity):
    cart_page.wait_for_product(product_name, present=True)
    actual = cart_page.quantity_for(product_name)
    assert actual == quantity, (
        f"Expected {product_name!r} with quantity {quantity}, got {actual}"
    )
