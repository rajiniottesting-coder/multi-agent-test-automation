"""Step definitions for features/product_categories.feature.

Binds the product-categories scenarios to ProductsPage methods. Every step the
feature uses is declared here, because pytest-bdd steps are module-scoped.

Rules observed:
- Step defs call page-object methods only; no selector strings here.
- Presence is asserted with waiting readers; absence with a non-waiting probe.
"""
from pytest_bdd import given, when, then, parsers, scenarios

from config.paths import feature_path

scenarios(str(feature_path("product_categories")))


# ─────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────

@given("I am on the products page")
def open_products_page(products_page, base_url):
    products_page.open_products(base_url)


@given(parsers.parse('I am on the category page for category id "{category_id}"'))
def open_category_by_id(products_page, base_url, category_id):
    products_page.open_category(base_url, category_id)


# ─────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────

@when(parsers.parse('I open the "{category}" category and select the "{subcategory}" subcategory'))
def open_category_from_sidebar(products_page, category, subcategory):
    products_page.open_category_from_sidebar(category, subcategory)


# ─────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────

@then("I should be on a category products page")
def assert_on_category_page(products_page):
    assert products_page.is_on_category_page(), "Expected to be on a category products page"


@then(parsers.parse('the category heading should be "{expected}"'))
def assert_category_heading(products_page, expected):
    assert products_page.category_heading_matches(expected), (
        f"Expected category heading {expected!r}, got {products_page.category_heading()!r}"
    )


@then("at least one product card should be displayed")
def assert_has_product_cards(products_page):
    assert products_page.has_product_cards(), "Expected at least one product card"


@then("no product cards should be displayed")
def assert_no_product_cards(products_page):
    assert products_page.has_no_product_cards(), "Expected no product cards to be displayed"
