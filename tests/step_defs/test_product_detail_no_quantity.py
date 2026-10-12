"""Step definitions for features/product_detail_no_quantity.feature.

SCRUM-232: the product detail page should no longer offer a quantity input.

Rules applied here:
- Declare EVERY step the feature uses in this module (steps are module-scoped).
- Call page-object methods only; no selectors in step definitions.
- Assert PRESENCE with a waiting reader, ABSENCE with a non-waiting probe.
"""
from pytest_bdd import given, when, then, parsers, scenarios

from config.paths import feature_path

scenarios(str(feature_path("product_detail_no_quantity")))


# ─────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────

@given("I am on the all products page")
def open_all_products(products_page, base_url):
    products_page.open_products(base_url)


# ─────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────

@when(parsers.parse('I open the product detail page for "{product_name}"'))
def open_product_detail(products_page, product_name):
    products_page.open_product_details(product_name)


# ─────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────

@then(parsers.parse('I should see the product name "{expected_name}"'))
def assert_product_name(product_detail_page, expected_name):
    actual = product_detail_page.product_name()
    assert expected_name in actual, f"Expected product name {expected_name!r} in {actual!r}"


@then(parsers.parse('I should see the product price "{expected_price}"'))
def assert_product_price(product_detail_page, expected_price):
    actual = product_detail_page.product_price()
    assert expected_price in actual, f"Expected price {expected_price!r} in {actual!r}"


@then("I should not see a quantity input field")
def assert_no_quantity_input(product_detail_page):
    assert not product_detail_page.has_quantity_input(), (
        "Expected no quantity input field on the product detail page"
    )
