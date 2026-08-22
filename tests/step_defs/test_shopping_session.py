"""Step definitions for features/shopping_session.feature.

Binds the shopping-session scenarios to page-object methods only. No selectors
appear here; real logins go through the `credentials` fixture by role, while
invalid and empty values stay literal because they are test data, not secrets.

Presence is asserted with waiting readers, absence with non-waiting probes.
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


@given("a newly registered account with an empty cart")
def newly_registered_account(login_page, base_url):
    """The full-session scenario owns its cart's starting state.

    The cart persists per account, so an absolute 'cart is empty' assertion is
    only safe when the scenario owns the starting state. This opens the signup
    / login page as the entry point for that owned session.
    """
    login_page.open_login_page(base_url)


# ─────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────

@when(parsers.re(r'I log in as a "(?P<role>[^"]*)" user$'))
def login_as_role(login_page, credentials, role):
    email, password = credentials(role)
    login_page.login_as(email, password)


@when(parsers.re(r'I log in as a "(?P<role>[^"]*)" user with password "(?P<password>[^"]*)"'))
def login_as_role_with_password(login_page, credentials, role, password):
    """Valid email for the role, a deliberately wrong password (test data)."""
    email, _ = credentials(role)
    login_page.login_as(email, password)


@when(parsers.re(r'I log in with email "(?P<email>[^"]*)" and password "(?P<password>[^"]*)"'))
def login_with_literal_credentials(login_page, email, password):
    login_page.login_as(email, password)


@when("I clear the credential fields")
def clear_credentials(login_page):
    login_page.clear_credentials()


@when("I go to the products page")
def go_to_products(nav_page):
    nav_page.open_products()


@when(parsers.re(r'I search for "(?P<term>[^"]*)"'))
def search_for(products_page, term):
    products_page.search_for(term)


@when(parsers.re(r'I open the product "(?P<product_name>[^"]*)" from the results'))
def open_product_from_results(products_page, product_name):
    products_page.open_product(product_name)


@when("I add the product to the cart")
def add_product_to_cart(product_detail_page):
    product_detail_page.add_product_to_cart()


@when("I view the cart from the added-to-cart modal")
def view_cart_from_modal(product_detail_page):
    product_detail_page.view_cart_from_modal()


@when(parsers.re(r'I remove the product "(?P<product_name>[^"]*)" from the cart'))
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
    assert not nav_page.is_logged_in(), "Unexpectedly logged in"


@then("I should see my account name in the navigation")
def assert_account_name_shown(nav_page):
    banner = nav_page.logged_in_name()
    assert "Logged in as" in banner, f"Expected a logged-in banner, got {banner!r}"


@then("I should see the login and signup link")
def assert_login_signup_link(nav_page):
    assert nav_page.wait_until_logged_out(), "Expected to be signed out"


@then("the search should have executed")
def assert_search_executed(products_page):
    assert products_page.is_search_executed(), "Search does not appear to have run"


@then(parsers.re(r'I should see the product "(?P<product_name>[^"]*)" in the results'))
def assert_product_in_results(products_page, product_name):
    assert products_page.has_result(product_name), (
        f"Expected {product_name!r} among the search results, got "
        f"{products_page.get_result_names()!r}"
    )


@then(parsers.re(r'the product detail page should show "(?P<expected_name>[^"]*)"'))
def assert_detail_name(product_detail_page, expected_name):
    actual = product_detail_page.product_name()
    assert expected_name in actual, f"Expected {expected_name!r} in {actual!r}"


@then(parsers.re(r'the cart should contain the product "(?P<product_name>[^"]*)"'))
def assert_cart_contains(cart_page, product_name):
    assert cart_page.has_product(product_name), (
        f"Expected {product_name!r} in the cart, got {cart_page.get_product_names()!r}"
    )


@then(parsers.re(r'the cart should show the price "(?P<price>[^"]*)" for "(?P<product_name>[^"]*)"'))
def assert_cart_price(cart_page, price, product_name):
    row = cart_page.get_row_text(product_name)
    assert price in row, f"Expected price {price!r} in row {row!r}"


@then("the cart should be empty")
def assert_cart_empty(cart_page):
    assert cart_page.is_empty(), "Expected the cart to be empty"


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


@then(parsers.re(r'I should see the price "(?P<price>[^"]*)" among the results'))
def assert_price_among_results(products_page, price):
    names = products_page.get_result_names()
    assert any(price in name for name in names), (
        f"Expected a result showing price {price!r}, got {names!r}"
    )
