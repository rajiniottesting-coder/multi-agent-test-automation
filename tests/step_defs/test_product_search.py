"""Step definitions for features/product_search.feature.

Binds the product-search scenarios to ProductsPage methods. Every step
interacts with the UI exclusively through page-object methods; no selectors
appear here.

Rules exercised:
- PRESENCE is asserted with waiting readers (is_search_results_shown,
  is_full_listing_shown, has_product); ABSENCE is asserted with the
  non-waiting probe has_no_product_cards().
- parsers.re with [^"]* matches the empty-query scenario where parsers.parse
  cannot match "".
"""
from pytest_bdd import given, when, then, parsers, scenarios

from config.paths import feature_path

scenarios(str(feature_path("product_search")))


# ─────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────

@given("I am on the products page")
def open_products_page(products_page, base_url):
    products_page.open_products(base_url)


# ─────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────

@when(parsers.re(r'I search for "(?P<term>[^"]*)"'))
def search_for_term(products_page, term):
    products_page.search_for(term)


# ─────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────

@then("the search results heading should be shown")
def assert_search_results_heading(products_page):
    assert products_page.is_search_results_shown(), \
        "Expected the Searched Products heading to be shown"


@then("the full product listing heading should be shown")
def assert_full_listing_heading(products_page):
    assert products_page.is_full_listing_shown(), \
        "Expected the All Products heading to remain shown"


@then(parsers.re(r'the search results should include "(?P<product_name>[^"]*)"'))
def assert_results_include(products_page, product_name):
    assert products_page.has_product(product_name), \
        f"Expected {product_name!r} among the products shown"


@then(parsers.re(r'every product in the results should match "(?P<term>[^"]*)"'))
def assert_every_product_matches(products_page, term):
    assert products_page.all_products_match(term), \
        f"Expected every product shown to match {term!r}"


@then("no product cards should be shown")
def assert_no_product_cards(products_page):
    assert products_page.has_no_product_cards(), \
        "Expected no product cards to be shown"
