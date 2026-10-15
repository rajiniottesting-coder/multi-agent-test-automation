"""Step definitions for features/shopper_session.feature.

Binds the shopper-session scenarios to the login, nav, products,
product-detail and cart page objects. Selectors never appear here — every
UI interaction goes through a page-object method. Real credentials are
resolved by role through the `credentials` fixture; invalid data stays
literal because it is test data, not a secret.

Presence is asserted with WAITING readers; absence with non-waiting probes
or waiting-for-absence helpers, never by negating a waiting presence check.
"""
from pytest_bdd import given, when, then, parsers, scenarios

from config.paths import feature_path

scenarios(str(feature_path("shopper_session")))


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
    """Literal values, for invalid and empty-field scenarios."""
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


@when("I submit the search with no term")
def submit_empty_search(products_page):
    products_page.submit_empty_search()


@when(parsers.parse('I view the product "{product_name}" from the search results'))
def view_product_from_results(products_page, product_name):
    products_page.open_product_details(product_name)


@when("I add the product to the cart")
def add_product_to_cart(product_detail_page):
    product_detail_page.add_to_cart()


@when("I view the cart from the added-to-cart modal")
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


@then("I should not be logged in")
def assert_not_logged_in(nav_page):
    """Non-waiting probe. The waiting reader would time out rather than
    return False, so the assertion would never be reached."""
    assert not nav_page.is_logged_in(), "Unexpectedly logged in"


@then("I should see my account name in the navigation")
def assert_account_name_shown(nav_page):
    banner = nav_page.logged_in_name()
    assert "Logged in as" in banner, f"Expected a logged-in banner, got {banner!r}"


@then(parsers.parse('the search results should include "{product_name}"'))
def assert_search_includes(products_page, product_name):
    assert products_page.is_search_results_shown(), "Search results view did not appear"
    assert products_page.has_product(product_name), (
        f"Expected {product_name!r} among the search results"
    )


@then(parsers.parse('I should be on the product detail page for "{product_name}"'))
def assert_on_product_detail(product_detail_page, product_name):
    assert product_detail_page.is_loaded(), "Product detail page did not load"
    actual = product_detail_page.product_name()
    assert product_name in actual, f"Expected detail page for {product_name!r}, got {actual!r}"


@then(parsers.parse('the product price should be "{expected_price}"'))
def assert_product_price(product_detail_page, expected_price):
    actual = product_detail_page.product_price()
    assert expected_price in actual, f"Expected price {expected_price!r}, got {actual!r}"


@then(parsers.parse('the cart should contain a row for "{product_name}"'))
def assert_cart_contains(cart_page, product_name):
    cart_page.wait_for_product(product_name, present=True)
    assert cart_page.has_product(product_name), (
        f"Expected a cart row for {product_name!r}"
    )


@then(parsers.parse('the cart should no longer contain a row for "{product_name}"'))
def assert_cart_absent(cart_page, product_name):
    cart_page.wait_for_product(product_name, present=False)
    assert cart_page.is_product_absent(product_name), (
        f"Expected no cart row for {product_name!r}"
    )


@then(parsers.re(r'I should see the error message "(?P<expected_message>[^"]*)"'))
def assert_error_message(login_page, expected_message):
    actual = login_page.get_login_error()
    assert expected_message in actual, f"Expected {expected_message!r} in {actual!r}"


@then("no product result cards should be displayed")
def assert_no_product_cards(products_page):
    assert products_page.has_no_product_cards(), (
        "Expected no product result cards to be displayed"
    )


@then("the unsearched products heading should remain")
def assert_unsearched_heading(products_page):
    assert products_page.is_full_listing_shown(), (
        "Expected the unsearched 'All Products' heading to remain"
    )
