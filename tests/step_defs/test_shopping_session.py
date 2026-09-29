"""Step definitions for features/shopping_session.feature.

Binds the shopping-session scenarios to page-object methods. Selectors never
appear here — every UI interaction goes through a page object. Real credentials
are resolved by ROLE via the `credentials` fixture; invalid data stays literal.

Presence is asserted with waiting readers; absence with non-waiting probes.
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


@given("I am on the products page")
def open_products_page_given(products_page, base_url):
    products_page.open_products_page(base_url)


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
    """Literal values, for invalid-credential scenarios."""
    login_page.login_as(email, password)


@when("I clear the credential fields")
def clear_credentials(login_page):
    login_page.clear_credentials()


@when("I open the products page")
def open_products_page_when(products_page, base_url):
    products_page.open_products_page(base_url)


@when(parsers.re(r'I search for "(?P<term>[^"]*)"'))
def search_for(products_page, term):
    products_page.search_for(term)


@when(parsers.re(r'I open the product detail for "(?P<product_name>[^"]*)"'))
def open_product_detail(products_page, product_name):
    products_page.open_product_detail_for(product_name)


@when("I add the product to the cart from the detail page")
def add_to_cart_from_detail(product_detail_page):
    product_detail_page.add_to_cart()


@when("I view the cart from the added modal")
def view_cart_from_modal(product_detail_page):
    product_detail_page.view_cart_from_modal()


@when(parsers.re(r'I remove "(?P<product_name>[^"]*)" from the cart'))
def remove_from_cart(cart_page, product_name):
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


@then("I should see my account name in the navigation")
def assert_account_name_shown(nav_page):
    banner = nav_page.logged_in_name()
    assert "Logged in as" in banner, f"Expected a logged-in banner, got {banner!r}"


@then("I should not be logged in")
def assert_not_logged_in(nav_page):
    """Non-waiting probe: the waiting reader would time out rather than
    return False, so the assertion would never be reached."""
    assert not nav_page.is_logged_in(), "Unexpectedly logged in"


@then("I should see the login and signup forms")
def assert_login_forms_visible(login_page):
    assert login_page.is_loaded(), "Expected the login and signup forms"


@then("I should see the login and signup link")
def assert_signup_login_link_visible(nav_page):
    assert nav_page.wait_until_logged_out(), "Expected the Signup / Login link"


@then("I should see the all products listing")
def assert_all_products_listing(products_page):
    assert products_page.is_showing_all_products(), "Expected the All Products listing"


@then(parsers.re(r'the search results should include "(?P<product_name>[^"]*)"'))
def assert_search_includes(products_page, product_name):
    assert products_page.has_result_for(product_name), (
        f"Expected {product_name!r} in the search results"
    )


@then(parsers.re(r'the product detail name should be "(?P<expected_name>[^"]*)"'))
def assert_detail_name(product_detail_page, expected_name):
    actual = product_detail_page.product_name()
    assert actual == expected_name, f"Expected name {expected_name!r}, got {actual!r}"


@then(parsers.re(r'the product detail price should contain "(?P<expected_price>[^"]*)"'))
def assert_detail_price(product_detail_page, expected_price):
    actual = product_detail_page.product_price()
    assert expected_price in actual, f"Expected {expected_price!r} in {actual!r}"


@then(parsers.re(r'the cart should contain "(?P<product_name>[^"]*)"'))
def assert_cart_contains(cart_page, product_name):
    assert cart_page.has_product(product_name), (
        f"Expected the cart to contain {product_name!r}"
    )


@then(parsers.re(r'the cart should no longer contain "(?P<product_name>[^"]*)"'))
def assert_cart_removed(cart_page, product_name):
    cart_page.wait_product_removed(product_name)


@then(parsers.re(r'I should see the error message "(?P<expected_message>[^"]*)"'))
def assert_error_message(login_page, expected_message):
    actual = login_page.get_login_error()
    assert expected_message in actual, f"Expected {expected_message!r} in {actual!r}"


@then("I should remain on the login page")
def assert_still_on_login(login_page):
    assert login_page.is_loaded(), "Expected to stay on the login page"


@then("no product cards should be displayed")
def assert_no_product_cards(products_page):
    count = products_page.get_result_card_count()
    assert count == 0, f"Expected zero product cards, found {count}"
