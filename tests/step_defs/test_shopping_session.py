"""Step definitions for features/shopping_session.feature.

Binds the end-to-end shopping-session scenarios to page-object methods.
Every step the feature uses is declared here — steps are module-scoped, so a
step defined in another module is not visible from this one.

Rules followed:
- Call page-object methods only; no selectors in this file.
- Log in by ROLE via the `credentials` fixture; invalid data stays literal.
- Assert PRESENCE with waiting readers and ABSENCE with non-waiting probes.
"""
from pytest_bdd import given, when, then, parsers, scenarios

from config.paths import feature_path

scenarios(str(feature_path("shopping_session")))


# ─────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────

@given("I am on the signup and login page")
def open_login_page(login_page, base_url):
    login_page.open_login_page(base_url)


# ─────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────

@when(parsers.re(r'I log in as a "(?P<role>[^"]*)" user$'))
def login_as_role(login_page, credentials, role):
    """Log in with real credentials resolved from the environment."""
    email, password = credentials(role)
    login_page.login_as(email, password)


@when(parsers.re(r'I log in with email "(?P<email>[^"]*)" and password "(?P<password>[^"]*)"'))
def login_with_literal_credentials(login_page, email, password):
    """Literal values for the invalid-credentials scenario."""
    login_page.login_as(email, password)


@when("I go to the products page")
def go_to_products_page(nav_page):
    nav_page.go_to_products()


@when(parsers.re(r'I search for "(?P<term>[^"]*)"'))
def search_for_term(products_page, term):
    products_page.search_for(term)


@when(parsers.re(r'I open the product "(?P<product_name>[^"]*)" from the search results'))
def open_product_from_results(products_page, product_name):
    products_page.open_product(product_name)


@when("I add the product to the cart")
def add_product_to_cart(product_detail_page):
    product_detail_page.add_to_cart()


@when("I view the cart from the modal")
def view_cart_from_modal(product_detail_page):
    product_detail_page.view_cart_from_modal()


@when(parsers.re(r'I remove "(?P<product_name>[^"]*)" from the cart'))
def remove_product_from_cart(cart_page, product_name):
    cart_page.remove_product(product_name)


@when("I log out")
def log_out(nav_page):
    nav_page.logout()


# ─────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────

@then("I should be logged in")
def assert_logged_in(nav_page):
    assert nav_page.wait_until_logged_in(), "No session after logging in"


@then("I should not be logged in")
def assert_not_logged_in(nav_page):
    """Non-waiting probe — the waiting reader would time out instead of
    returning False, so the assertion would never be reached."""
    assert not nav_page.is_logged_in(), "Unexpectedly logged in"


@then("I should be logged out")
def assert_logged_out(nav_page):
    assert nav_page.wait_until_logged_out(), "Still logged in after logout"


@then("I should see my account name in the navigation")
def assert_account_name_shown(nav_page):
    banner = nav_page.logged_in_name()
    assert "Logged in as" in banner, f"Expected a logged-in banner, got {banner!r}"


@then(parsers.re(r'the search results should include "(?P<product_name>[^"]*)"'))
def assert_results_include(products_page, product_name):
    assert products_page.result_includes(product_name), \
        f"Expected {product_name!r} in the search results"


@then(parsers.re(r'the product detail page should show "(?P<product_name>[^"]*)"'))
def assert_detail_shows(product_detail_page, product_name):
    actual = product_detail_page.product_name()
    assert actual == product_name, f"Expected {product_name!r}, got {actual!r}"


@then(parsers.re(r'the cart should contain "(?P<product_name>[^"]*)"'))
def assert_cart_contains(cart_page, product_name):
    assert cart_page.has_product(product_name), \
        f"Expected the cart to contain {product_name!r}"


@then(parsers.re(r'the cart should no longer contain "(?P<product_name>[^"]*)"'))
def assert_cart_excludes(cart_page, product_name):
    cart_page.wait_until_product_removed(product_name)


@then(parsers.re(r'I should see the error message "(?P<expected_message>[^"]*)"'))
def assert_error_message(login_page, expected_message):
    actual = login_page.get_login_error()
    assert expected_message in actual, f"Expected {expected_message!r} in {actual!r}"


@then("no product result cards should be displayed")
def assert_no_result_cards(products_page):
    assert products_page.has_no_result_cards(), \
        "Expected no product result cards for the search term"
