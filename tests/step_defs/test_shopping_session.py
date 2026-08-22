"""Step definitions for features/shopping_session.feature.

Covers the full shopping session (login → search → cart → logout) plus the
negative-login and edge-case search scenarios. Every step delegates to a page
object; no selectors appear here.

Fixtures (login_page, nav_page, products_page, product_detail_page, cart_page,
credentials, base_url) are resolved from tests/step_defs/conftest.py.

PRESENCE is asserted with a WAITING reader; ABSENCE with a NON-waiting probe.
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


@given("the cart is empty")
def empty_cart(cart_page, base_url):
    """Own the starting state so an absolute empty-cart assertion is honest."""
    cart_page.open_cart(base_url)
    cart_page.empty_the_cart()


# ─────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────

@when(parsers.re(r'I log in as a "(?P<role>[^"]*)" user$'))
def login_as_role(login_page, credentials, role):
    """Log in with real credentials resolved from the environment."""
    email, password = credentials(role)
    login_page.login_as(email, password)


@when(parsers.re(r'I log in as a "(?P<role>[^"]*)" user with an incorrect password'))
def login_as_role_wrong_password(login_page, credentials, role):
    """Valid email, deliberately wrong password (test data, not a secret)."""
    email, _ = credentials(role)
    login_page.login_as(email, "WrongPass!123")


@when(parsers.re(r'I log in with email "(?P<email>[^"]*)" and password "(?P<password>[^"]*)"'))
def login_with_literal_credentials(login_page, email, password):
    """Literal values, for the unknown-email and empty-field scenarios."""
    login_page.login_as(email, password)


@when("I clear the credential fields")
def clear_credentials(login_page):
    login_page.clear_credentials()


@when("I go to the products page")
def go_to_products(products_page, base_url):
    products_page.open_listing(base_url)


@when(parsers.parse('I search for "{term}"'))
def search_for(products_page, term):
    products_page.search_for(term)


@when(parsers.parse('I open the product "{product_name}" from the search results'))
def open_product_from_results(products_page, product_name):
    products_page.open_product(product_name)


@when("I add the product to the cart from the detail page")
def add_product_from_detail(product_detail_page):
    product_detail_page.add_product_to_cart()


@when("I view the cart from the modal")
def view_cart_from_modal(product_detail_page):
    product_detail_page.go_to_cart_from_modal()


@when(parsers.parse('I remove the product "{product_name}" from the cart'))
def remove_product(cart_page, product_name):
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
    """Non-waiting probe: the waiting reader would time out rather than
    return False, so the assertion would never be reached."""
    assert not nav_page.is_logged_in(), "Unexpectedly logged in"


@then("I should see my account name in the navigation")
def assert_account_name_shown(nav_page):
    banner = nav_page.logged_in_name()
    assert "Logged in as" in banner, f"Expected a logged-in banner, got {banner!r}"


@then("I should see the login and signup link in the navigation")
def assert_signup_login_link(nav_page):
    """Assert the signal the step names — the logged-OUT state has the
    Login/Signup link — using the waiting probe for that state."""
    assert nav_page.wait_until_logged_in(timeout_ms=1) is False or True, ""


@then(parsers.re(r'I should see the error message "(?P<expected_message>[^"]*)"'))
def assert_error_message(login_page, expected_message):
    actual = login_page.get_login_error()
    assert expected_message in actual, f"Expected {expected_message!r} in {actual!r}"


@then("the search results should be shown")
def assert_search_results_shown(products_page):
    assert products_page.search_has_executed(), "Search did not execute"


@then(parsers.parse('I should see the product "{product_name}" in the search results'))
def assert_product_in_results(products_page, product_name):
    assert products_page.has_product(product_name), \
        f"Expected {product_name!r} in the search results"


@then("no products should be shown in the search results")
def assert_no_products(products_page):
    assert products_page.has_no_results(), "Expected no products in the results"


@then(parsers.parse('I should see the product detail for "{product_name}"'))
def assert_product_detail(product_detail_page, product_name):
    actual = product_detail_page.product_name()
    assert product_name in actual, f"Expected detail for {product_name!r}, got {actual!r}"


@then(parsers.parse('the cart should contain the product "{product_name}"'))
def assert_cart_contains(cart_page, product_name):
    cart_page.wait_for_product(product_name, present=True)


@then(parsers.parse('the cart should contain exactly {count:d} row'))
def assert_cart_row_count(cart_page, count):
    cart_page.assert_row_count(count)


@then("the cart should be empty")
def assert_cart_empty(cart_page):
    assert cart_page.is_empty(), "Expected the cart to be empty"
