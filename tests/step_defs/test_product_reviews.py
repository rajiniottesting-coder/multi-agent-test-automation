"""Step definitions for features/product_reviews.feature.

Covers the product review form on a product's details page: the positive
submission flow, the form's presence for an unauthenticated shopper, and the
negative cases where a required field is left empty.

Conventions (see tests/step_defs/test_login.py reference):
- Declare EVERY step the feature uses here; steps are module-scoped.
- Call page-object methods only — no selectors in step definitions.
- Use parsers.re with [^"]* where a quoted value can be empty; parsers.parse
  cannot match "".
- Assert PRESENCE with a waiting reader and ABSENCE with a non-waiting probe.
"""
from pytest_bdd import given, when, then, parsers, scenarios

from config.paths import feature_path

scenarios(str(feature_path("product_reviews")))


# ─────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────

@given("I am on the products listing page")
def open_products_listing(products_page, base_url):
    products_page.open_products(base_url)


# ─────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────

@when(parsers.re(r'I open the product details page for "(?P<product_name>[^"]*)"'))
def open_product_details(products_page, product_name):
    products_page.open_product_details(product_name)


@when(parsers.re(r'I submit a review with name "(?P<name>[^"]*)" email "(?P<email>[^"]*)" and review text "(?P<text>[^"]*)"'))
def submit_product_review(product_detail_page, name, email, text):
    product_detail_page.submit_review(name, email, text)


# ─────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────

@then(parsers.re(r'the products listing should show "(?P<product_name>[^"]*)"'))
def assert_products_listing_shows(products_page, product_name):
    assert products_page.has_product(product_name), \
        f"Expected {product_name!r} in the products listing"


@then("the login prompt should not be shown on the products page")
def assert_no_login_prompt(nav_page):
    assert not nav_page.is_logged_in(), \
        "Expected no session, but the shopper appears to be signed in"


@then("the Write Your Review form should be shown on the product details page")
def assert_review_form_shown(product_detail_page):
    assert product_detail_page.has_review_form(), \
        "Write Your Review form is not shown on the product details page"


@then(parsers.re(r'I should see the review confirmation message "(?P<expected_message>[^"]*)"'))
def assert_review_confirmation(product_detail_page, expected_message):
    actual = product_detail_page.get_review_success()
    assert actual == expected_message, f"Expected {expected_message!r}, got {actual!r}"


@then("the review thank-you message should not be shown")
def assert_no_review_confirmation(product_detail_page):
    assert product_detail_page.is_review_success_absent(), \
        "Review thank-you message was unexpectedly shown"
