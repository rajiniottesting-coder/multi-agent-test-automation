"""Step definitions for features/shopping_session.feature.

Covers the full shopping session (login, search, add to cart, remove, logout)
plus negative login and search edge cases. Every step delegates to a
page-object method; no selectors or DOM logic live here.

Page-object fixtures (login_page, nav_page, products_page, product_detail_page,
cart_page) and the credentials fixture resolve from tests/step_defs/conftest.py.
Absence is asserted with non-waiting probes; presence with waiting readers.
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
# When — authentication
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
    """Literal values, for unknown-email and empty-field scenarios."""
    login_page.login_as(email, password)


@when("I clear the credential fields")
def clear_credentials(login_page):
    login_page.clear_credentials()


@when("I log out from the navigation")
def logout(nav_page):
    nav_page.logout()


# ─────────────────────────────────────────────────────────────
# When — browsing and cart
# ─────────────────────────────────────────────────────────────

@when("I open the products listing from the navigation")
def open_products_listing(nav_page):
    nav_page.go_to_products()


@when(parsers.parse('I search for "{term}"'))
def search_for(products_page, term):
    products_page.search_for(term)


@when(parsers.parse('I open the product "{product_name}" from the results'))
def open_product_from_results(products_page, product_name):
    products_page.open_product(product_name)


@when("I add the product to the cart")
def add_product_to_cart(product_detail_page):
    product_detail_page.add_product_to_cart()


@when("I view the cart from the added-to-cart modal")
def view_cart_from_modal(product_detail_page):
    product_detail_page.open_cart_from_modal()


@when(parsers.parse('I remove the product "{product_name}" from the cart'))
def remove_product_from_cart(cart_page, product_name):
    cart_page.remove_product(product_name)


# ─────────────────────────────────────────────────────────────
# Then — authentication
# ─────────────────────────────────────────────────────────────

@then("I should be logged in")
def assert_logged_in(nav_page):
    assert nav_page.wait_until_logged_in(), "No session after logging in"


@then("I should not be logged in")
def assert_not_logged_in(nav_page):
    assert not nav_page.is_logged_in(), "Unexpectedly logged in"


@then("I should see my account name in the navigation")
def assert_account_name_shown(nav_page):
    banner = nav_page.logged_in_name()
    assert "Logged in as" in banner, f"Expected a logged-in banner, got {banner!r}"


@then(parsers.re(r'I should see the error message "(?P<expected_message>[^"]*)"'))
def assert_error_message(login_page, expected_message):
    actual = login_page.get_login_error()
    assert expected_message in actual, f"Expected {expected_message!r} in {actual!r}"


@then("I should remain on the login page")
def assert_still_on_login(login_page):
    assert login_page.is_loaded(), "Expected to stay on the login page"


@then("I should remain on the login page")
def assert_remain_on_login(login_page):
    assert login_page.is_loaded(), "Expected to stay on the login page"


# ─────────────────────────────────────────────────────────────
# Then — browsing and cart
# ─────────────────────────────────────────────────────────────

@then("the search should have executed")
def assert_search_executed(products_page):
    assert products_page.has_searched(), "Search does not appear to have executed"


@then(parsers.parse('I should see the product "{product_name}" in the results'))
def assert_product_in_results(products_page, product_name):
    assert products_page.has_result(product_name), (
        f"Expected {product_name!r} in results, got {products_page.get_result_names()!r}"
    )


@then("no products should be shown in the results")
def assert_no_results(products_page):
    products_page.assert_result_card_count(0)


@then(parsers.parse('I should be on the product detail page for "{product_name}"'))
def assert_on_product_detail(product_detail_page, product_name):
    assert product_detail_page.is_loaded(), "Product detail page did not load"
    actual = product_detail_page.product_name()
    assert product_name in actual, f"Expected {product_name!r} in {actual!r}"


@then(parsers.parse('the cart should contain the product "{product_name}"'))
def assert_cart_contains(cart_page, product_name):
    cart_page.wait_for_product_row(product_name, present=True)
    assert cart_page.has_product(product_name), (
        f"Expected {product_name!r} in cart, got {cart_page.get_product_names()!r}"
    )


@then(parsers.parse('the cart should have exactly {count:d} product row'))
def assert_cart_row_count(cart_page, count):
    cart_page.assert_row_count(count)


@then("the cart should be empty")
def assert_cart_empty(cart_page):
    assert cart_page.is_empty(), "Expected the cart to be empty"
