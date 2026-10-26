"""Step definitions for features/shopping_session.feature.

Every step the feature uses is declared here — pytest-bdd steps are
module-scoped, so a step defined in another module is invisible to this one.
Step definitions call page-object methods only; no selectors appear here.

Reused Then sentences assert EXACTLY what their committed definitions assert.

Cart note: the cart page is declared persistent_state — the application keeps
it against the signed-in account, and this app declares no way to establish a
clean start. So cart assertions here are RELATIVE: that the product this
scenario added is present, or is gone. That holds whatever the cart started as.
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
    """Literal values, for the invalid-credentials scenario."""
    login_page.login_as(email, password)


@when("I go to the products page")
def go_to_products(nav_page):
    nav_page.go_to_products()


@when(parsers.re(r'I search for "(?P<term>[^"]*)"'))
def search_for_term(products_page, term):
    products_page.search_for(term)


@when(parsers.re(r'I open the product "(?P<product_name>[^"]*)" from the search results'))
def open_product_from_results(products_page, product_name):
    products_page.view_product_from_results(product_name)


@when("I add the product to the cart")
def add_product_to_cart(product_detail_page):
    product_detail_page.add_to_cart()


@when("I view the cart from the product modal")
def view_cart_from_modal(product_detail_page):
    product_detail_page.view_cart()


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
    """The Logout link is rendered only while authenticated, which is more
    reliable than the URL: this app serves the same path either way."""
    assert nav_page.wait_until_logged_in(), "No session after logging in"


@then("I should see my account name in the navigation")
def assert_account_name_shown(nav_page):
    banner = nav_page.logged_in_name()
    assert "Logged in as" in banner, f"Expected a logged-in banner, got {banner!r}"


@then(parsers.re(r'the search results should include "(?P<product_name>[^"]*)"'))
def assert_results_include(products_page, product_name):
    assert products_page.has_product(product_name), \
        f"Expected {product_name!r} among the products shown"


@then(parsers.re(r'the product detail page shows the name "(?P<product_name>[^"]*)"'))
def assert_detail_name(product_detail_page, product_name):
    actual_name = product_detail_page.product_name()
    assert product_name in actual_name, \
        f"Expected product name {product_name!r}, got {actual_name!r}"


@then(parsers.re(r'the product detail page shows the price "(?P<price>[^"]*)"'))
def assert_detail_price(product_detail_page, price):
    actual_price = product_detail_page.product_price()
    assert price in actual_price, \
        f"Expected price {price!r}, got {actual_price!r}"


@then(parsers.re(r'the cart should list "(?P<product_name>[^"]*)"'))
def assert_cart_lists_product(cart_page, product_name):
    """RELATIVE assertion: the cart is persistent_state and this app offers no
    clean start, so we assert only that what THIS scenario added is present."""
    cart_page.wait_for_product(product_name, present=True)
    assert cart_page.has_product(product_name), \
        f"Expected {product_name!r} to be listed in the cart"


@then(parsers.re(r'"(?P<product_name>[^"]*)" should no longer be listed in the cart'))
def assert_product_removed(cart_page, product_name):
    """RELATIVE assertion: the product THIS scenario added is gone. Waits for
    the row to disappear rather than snapshotting the list, and never asserts
    an absolute empty state on this persistent_state page."""
    cart_page.wait_for_product(product_name, present=False)


@then("I should not be logged in")
def assert_not_logged_in(nav_page):
    """Non-waiting probe. The waiting reader would time out rather than
    return False, so the assertion would never be reached."""
    assert not nav_page.is_logged_in(), "Unexpectedly logged in"


@then("I should see the signup and login link in the navigation")
def assert_signup_login_shown(nav_page):
    assert nav_page.is_signup_login_shown(), \
        "Expected the Signup / Login link in the navigation"


@then(parsers.re(r'I should see the error message "(?P<expected_message>[^"]*)"'))
def assert_error_message(login_page, expected_message):
    actual = login_page.get_login_error()
    assert expected_message in actual, f"Expected {expected_message!r} in {actual!r}"


@then("I should remain on the login page")
def assert_still_on_login(login_page):
    assert login_page.is_loaded(), "Expected to stay on the login page"


@then("no product result cards should be shown")
def assert_no_product_cards(products_page):
    assert products_page.has_no_product_cards(), \
        "Expected no product result cards to be shown"
