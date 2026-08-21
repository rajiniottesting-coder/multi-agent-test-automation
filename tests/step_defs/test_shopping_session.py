"""Step definitions for features/shopping_session.feature.

Covers the full shopping session, invalid-login handling, and product-search
edge cases. Every step calls page-object methods only — no selectors here.

Presence is asserted with waiting readers; absence with non-waiting probes.
Login is by ROLE via the `credentials` fixture; invalid/empty data stays
literal because it is test data, not a credential.
"""
from pytest_bdd import given, when, then, parsers, scenarios

from config.paths import feature_path

scenarios(str(feature_path("shopping_session")))


# ─────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────

@given("a newly registered account is logged in")
def newly_registered_account_logged_in(login_page, nav_page, credentials, base_url):
    """Log in with the registered account so the session owns its own state."""
    login_page.open_login_page(base_url)
    email, password = credentials("registered")
    login_page.login_as(email, password)
    assert nav_page.wait_until_logged_in(), "No session after logging in"


@given("I am on the signup and login page")
def open_signup_login_page(login_page, base_url):
    login_page.open_login_page(base_url)


# ─────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────

@when("I open the products listing")
def open_products_listing(nav_page):
    nav_page.open_products()


@when(parsers.re(r'I search for "(?P<term>[^"]*)"'))
def search_for_term(products_page, term):
    products_page.search_for(term)


@when(parsers.re(r'I open the product "(?P<product_name>[^"]*)" from the results'))
def open_product_from_results(products_page, product_name):
    products_page.open_product(product_name)


@when("I add the product to the cart from the product detail page")
def add_product_to_cart(product_detail_page):
    product_detail_page.add_product_to_cart()


@when("I view the cart from the added-to-cart modal")
def view_cart_from_modal(product_detail_page):
    product_detail_page.open_cart_from_modal()


@when(parsers.re(r'I remove the product "(?P<product_name>[^"]*)" from the cart'))
def remove_product_from_cart(cart_page, product_name):
    cart_page.remove_product(product_name)


@when("I log out")
def log_out(nav_page):
    nav_page.logout()


@when(parsers.re(r'I log in as a "(?P<role>[^"]*)" user with an incorrect password'))
def login_as_role_wrong_password(login_page, credentials, role):
    """Valid email, deliberately wrong password (test data, not a secret)."""
    email, _ = credentials(role)
    login_page.login_as(email, "WrongPass!123")


@when("I clear the credential fields")
def clear_credential_fields(login_page):
    login_page.clear_credentials()


@when(parsers.re(r'I log in with email "(?P<email>[^"]*)" and password "(?P<password>[^"]*)"'))
def login_with_literal_credentials(login_page, email, password):
    """Literal values, for invalid and empty-field scenarios."""
    login_page.login_as(email, password)


# ─────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────

@then("the search results should be displayed")
def assert_search_results_displayed(products_page):
    assert products_page.search_executed(), "Search did not execute"


@then(parsers.re(r'I should see the product "(?P<product_name>[^"]*)" in the results'))
def assert_product_in_results(products_page, product_name):
    names = products_page.result_names()
    assert any(product_name in name for name in names), \
        f"Expected {product_name!r} among results, got {names!r}"


@then(parsers.re(r'the cart should contain the product "(?P<product_name>[^"]*)"'))
def assert_cart_contains_product(cart_page, product_name):
    cart_page.wait_for_product(product_name, present=True)
    row_text = cart_page.row_text_for(product_name)
    assert product_name in row_text, \
        f"Expected {product_name!r} in cart row, got {row_text!r}"


@then("the cart should be empty")
def assert_cart_empty(cart_page):
    assert cart_page.is_empty(), "Expected the cart to be empty"


@then("I should not be logged in")
def assert_not_logged_in(nav_page):
    """Non-waiting probe. A waiting reader would time out rather than
    return False, so the assertion would never be reached."""
    assert not nav_page.is_logged_in(), "Unexpectedly logged in"


@then("I should see the login and signup link in the navigation")
def assert_signup_login_visible(nav_page):
    assert nav_page.is_signup_login_visible(), \
        "Expected the Signup/Login link in the navigation"


@then(parsers.re(r'I should see the error message "(?P<expected_message>[^"]*)"'))
def assert_error_message(login_page, expected_message):
    actual = login_page.get_login_error()
    assert expected_message in actual, f"Expected {expected_message!r} in {actual!r}"


@then("no product cards should be shown")
def assert_no_product_cards(products_page):
    count = products_page.result_card_count()
    assert count == 0, f"Expected no product cards, found {count}"
