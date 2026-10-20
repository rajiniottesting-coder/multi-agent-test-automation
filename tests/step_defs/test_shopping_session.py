"""Step definitions for features/shopping_session.feature.

Binds the shopping-session scenarios to page-object methods. Steps are
module-scoped in pytest-bdd, so every phrase the feature uses is declared here,
including phrases that also exist in committed step files — each module resolves
its own copy. Reused Then steps assert exactly what their committed definitions
assert; nothing is added.

Page-object methods are called by name only; no selectors appear here. Real
logins go through the `credentials` fixture (by ROLE); invalid data stays
literal.
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


@when(parsers.re(r'I log in as a "(?P<role>[^"]*)" user with an incorrect password'))
def login_as_role_wrong_password(login_page, credentials, role):
    """Valid email, deliberately wrong password (test data, not a secret)."""
    email, _ = credentials(role)
    login_page.login_as(email, "definitely-not-the-password")


@when(parsers.re(r'I log in with email "(?P<email>[^"]*)" and password "(?P<password>[^"]*)"'))
def login_with_literal_credentials(login_page, email, password):
    """Literal values, for invalid-credential scenarios."""
    login_page.login_as(email, password)


@when("I clear the credential fields")
def clear_credentials(login_page):
    login_page.clear_credentials()


@when("I go to the products page")
def go_to_products(nav_page):
    nav_page.go_to_products()


@when(parsers.parse('I search for "{term}"'))
def search_for_term(products_page, term):
    products_page.search_for(term)


@when(parsers.parse('I open the product "{product_name}" from the search results'))
def open_product_from_results(products_page, product_name):
    products_page.open_product_details(product_name)


@when("I add the product to the cart with the default quantity")
def add_to_cart_default_quantity(product_detail_page):
    product_detail_page.add_to_cart_with_default_quantity()


@when("I view the cart from the confirmation modal")
def view_cart_from_modal(product_detail_page):
    product_detail_page.view_cart()


@when(parsers.parse('I remove "{product_name}" from the cart'))
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


@then("the search results should be displayed")
def assert_search_results_displayed(products_page):
    assert products_page.is_search_results_shown(), "Expected the searched-products view"


@then(parsers.parse('I should see "{product_name}" in the search results'))
def assert_product_in_results(products_page, product_name):
    assert products_page.has_product(product_name), (
        f"Expected {product_name!r} in the search results"
    )


@then(parsers.parse('I should see the product name "{product_name}"'))
def assert_product_name(product_detail_page, product_name):
    actual = product_detail_page.product_name()
    assert product_name in actual, f"Expected product name {product_name!r}, got {actual!r}"


@then(parsers.parse('I should see the product price "{price}"'))
def assert_product_price(product_detail_page, price):
    actual = product_detail_page.product_price()
    assert price in actual, f"Expected price {price!r}, got {actual!r}"


@then("I should see the product added confirmation")
def assert_added_confirmation(product_detail_page):
    assert product_detail_page.has_added_confirmation(), (
        "Expected the add-to-cart confirmation modal"
    )


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


@then("I should not be logged in")
def assert_not_logged_in(nav_page):
    """Non-waiting probe. The waiting reader would time out rather than
    return False, so the assertion would never be reached."""
    assert not nav_page.is_logged_in(), "Unexpectedly logged in"


@then(parsers.re(r'I should see the error message "(?P<expected_message>[^"]*)"'))
def assert_error_message(login_page, expected_message):
    actual = login_page.get_login_error()
    assert expected_message in actual, f"Expected {expected_message!r} in {actual!r}"


@then("I should remain on the login page")
def assert_still_on_login(login_page):
    assert login_page.is_loaded(), "Expected to stay on the login page"


@then("there should be no product results")
def assert_no_product_results(products_page):
    assert products_page.has_no_product_cards(), "Expected no product result cards"
