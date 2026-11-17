"""Step definitions for features/cart_delete_last_product.feature.

Regression coverage for SCRUM-452: deleting the only product from the cart must
show the empty-cart message and leave no leftover row.

Conventions (copied from the login reference):
- Declare EVERY step the paired feature uses here; steps are module-scoped.
- Call page-object methods only — never a selector in a step definition.
- Assert PRESENCE with a waiting reader and ABSENCE with a non-waiting probe.
"""
from pytest_bdd import given, when, then, parsers, scenarios

from config.paths import feature_path

scenarios(str(feature_path("cart_delete_last_product")))


# ─────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────

@given("I am on the products page")
def open_products_page(products_page, base_url):
    products_page.open_products(base_url)


# ─────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────

@when(parsers.parse('I open the product details for "{product_name}"'))
def open_product_details(products_page, product_name):
    products_page.open_product_details(product_name)


@when("I add the product to the cart from the product details page")
def add_to_cart_from_details(product_detail_page):
    product_detail_page.add_to_cart()


@when("I view the cart from the confirmation modal")
def view_cart_from_modal(product_detail_page):
    product_detail_page.view_cart()


@when(parsers.parse('I delete the product "{product_name}" from the cart'))
def delete_product_from_cart(cart_page, product_name):
    cart_page.remove_product(product_name)


# ─────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────

@then(parsers.parse('I should see the product "{product_name}" in the cart'))
def assert_product_in_cart(cart_page, product_name):
    cart_page.wait_for_product(product_name, present=True)
    assert cart_page.has_product(product_name), f"Expected {product_name!r} in the cart"


@then(parsers.parse('the product "{product_name}" should not be shown in the cart'))
def assert_product_absent(cart_page, product_name):
    cart_page.wait_for_product(product_name, present=False)
    assert cart_page.is_product_absent(product_name), f"{product_name!r} is still in the cart"


@then("the cart should show the empty-cart message")
def assert_empty_cart_message(cart_page):
    assert cart_page.is_empty_cart_message_shown(), "Expected the empty-cart message"
