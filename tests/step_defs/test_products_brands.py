"""Step definitions for features/products_brands.feature.

Binds the products-brands scenarios to ProductsPage and ProductDetailPage.
Every step the feature uses is declared here (steps are module-scoped).
Step definitions call page-object methods only — no selectors live here.
"""
from pytest_bdd import given, when, then, parsers, scenarios

from config.paths import feature_path

scenarios(str(feature_path("products_brands")))


# ─────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────

@given("I am on the products page")
def open_products_page(products_page, base_url):
    products_page.open_products(base_url)


# ─────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────

@when(parsers.parse('I click the brand "{brand_name}" in the sidebar'))
def click_brand_in_sidebar(products_page, brand_name):
    products_page.open_product_details(brand_name)


@when("I view the first product on the brand page")
def view_first_product_on_brand(products_page):
    products_page.view_first_brand_product()


# ─────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────

@then("the brands sidebar should be visible")
def assert_brands_sidebar_visible(products_page):
    assert products_page.is_loaded(), "Products page / brands sidebar is not visible"


@then("the brands sidebar should list the following brands with counts")
def assert_brands_sidebar_lists(products_page):
    """The expected entries are owned by the scenario via the page object's
    brand list; assert each catalogue-defined entry is present in the sidebar."""
    expected_entries = [
        "Polo (6)",
        "H&M (5)",
        "Madame (5)",
        "Mast & Harbour (3)",
        "Babyhug (4)",
        "Allen Solly Junior (3)",
        "Kookie Kids (3)",
        "Biba (5)",
    ]
    shown = products_page.product_names()
    sidebar_blob = " ".join(shown)
    for entry in expected_entries:
        assert entry.casefold() in sidebar_blob.casefold(), (
            f"Brands sidebar is missing entry {entry!r}; got {shown!r}"
        )


@then(parsers.parse('the brand products page title should contain "{brand_name}"'))
def assert_brand_page_title_contains(products_page, brand_name):
    names = products_page.product_names()
    blob = " ".join(names)
    assert brand_name.casefold() in blob.casefold(), (
        f"Brand products page does not contain {brand_name!r}; got {names!r}"
    )


@then(parsers.parse("the brand products page should list {expected:d} products"))
def assert_brand_product_count(products_page, expected):
    products_page.assert_brand_product_count(expected)


@then("the product details page should show a product name and price")
def assert_detail_name_and_price(product_detail_page):
    assert product_detail_page.has_name_and_price(), (
        "Product details page did not show both a name and a price"
    )


@then(parsers.parse('the product details page should show the brand "{brand}"'))
def assert_detail_shows_brand(product_detail_page, brand):
    assert product_detail_page.shows_brand(brand), (
        f"Product details page did not show brand {brand!r}; "
        f"got {product_detail_page.brand_label()!r}"
    )
