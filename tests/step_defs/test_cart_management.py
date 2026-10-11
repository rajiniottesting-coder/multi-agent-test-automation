"""Step definitions for features/cart_management.feature.

Binds cart-management Gherkin steps to page-object methods. The cart in these
scenarios is the anonymous session cart (no sign-in), so quantity and presence
assertions are made against the products this test itself added.

Rules observed:
- Page-object methods only; no selectors in step definitions.
- PRESENCE asserted with waiting readers (wait_for_product / has_product).
- ABSENCE asserted with the waiting reader in present=False mode, which is the
  correct waiting form for a removal.
- Quantity is read from the cart's own quantity cell via quantity_for().
"""
from pytest_bdd import given, when, then, parsers, scenarios

from config.paths import feature_path

scenarios(str(feature_path("cart_management")))


# ─────────────────────────────────────────────────────────────
# Given / When — products listing
# ─────────────────────────────────────────────────────────────

@given("I am on the products listing page")
@when("I am on the products listing page")
def open_products_listing(products_page, base_url):
    products_page.open_products(base_url)


@when(parsers.parse('I open the product details page for "{product_name}"'))
def open_product_details(products_page, product_detail_page, product_name):
    products_page.open_product_details(product_name)
    assert product_detail_page.is_loaded(), (
        f"Product details page for {product_name!r} did not load"
    )


# ─────────────────────────────────────────────────────────────
# When — add to cart
# ─────────────────────────────────────────────────────────────

@when("I add the product to the cart and continue to the cart")
def add_and_view_cart(product_detail_page):
    product_detail_page.add_to_cart()
    product_detail_page.view_cart()


@when("I add the product to the cart and continue shopping")
def add_and_continue_shopping(product_detail_page):
    product_detail_page.add_to_cart()
    product_detail_page.continue_shopping()


# ─────────────────────────────────────────────────────────────
# When — cart actions
# ─────────────────────────────────────────────────────────────

@when(parsers.parse('I remove "{product_name}" from the cart'))
def remove_from_cart(cart_page, product_name):
    cart_page.remove_product(product_name)


# ─────────────────────────────────────────────────────────────
# Then — cart assertions
# ─────────────────────────────────────────────────────────────

@then(parsers.parse('the cart should contain "{product_name}" with quantity {quantity:d}'))
def assert_cart_contains_with_quantity(cart_page, product_name, quantity):
    cart_page.wait_for_product(product_name, present=True)
    actual = cart_page.quantity_for(product_name)
    assert actual == quantity, (
        f"Expected {product_name!r} with quantity {quantity}, got {actual}"
    )


@then(parsers.parse('the cart should not contain "{product_name}"'))
def assert_cart_does_not_contain(cart_page, product_name):
    cart_page.wait_for_product(product_name, present=False)
