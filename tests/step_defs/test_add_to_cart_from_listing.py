"""Step definitions for features/add_to_cart_from_listing.feature.

SCRUM-235: add a product to the cart directly from its listing card, without
opening the product detail page.

Conventions (mirroring tests/step_defs/test_login.py):
- Every step the feature uses is declared here; steps are module-scoped.
- Step bodies call page-object methods only — no selectors, no element keys.
- Presence is asserted with waiting page-object readers.
- The cart assertion is RELATIVE: it checks that the product THIS scenario
  added is present with the expected quantity, which holds whatever the cart
  started with (the cart persists for a session/account on this shared app).
"""
from pytest_bdd import given, when, then, parsers, scenarios

from config.paths import feature_path

scenarios(str(feature_path("add_to_cart_from_listing")))


# ─────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────

@given("I am on the products listing page")
def open_products_listing(products_page, base_url):
    products_page.open_products(base_url)


# ─────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────

@when(parsers.parse('I add "{product_name}" to the cart from its listing card'))
def add_product_from_listing(products_page, product_name):
    products_page.add_to_cart_from_listing(product_name)


@when("I click View Cart in the modal")
def click_view_cart_in_modal(products_page):
    products_page.open_cart_from_modal()


# ─────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────

@then("I should see the product added confirmation modal")
def assert_added_modal(products_page):
    assert products_page.is_added_modal_shown(), "Add-to-cart confirmation modal did not appear"


@then("I should be on the cart page")
def assert_on_cart_page(cart_page):
    assert cart_page.is_loaded(), "Expected to be on the cart page"


@then(parsers.parse('the cart should contain "{product_name}" with quantity {quantity:d}'))
def assert_cart_contains_product_with_quantity(cart_page, product_name, quantity):
    cart_page.wait_for_product(product_name, present=True)
    actual = cart_page.quantity_for(product_name)
    assert actual == quantity, (
        f"Expected quantity {quantity} for {product_name!r}, got {actual}"
    )
