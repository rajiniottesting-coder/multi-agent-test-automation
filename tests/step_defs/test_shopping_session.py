"""Step definitions for features/shopping_session.feature.

Binds the shopping-session scenarios to page-object methods. Selectors never
appear here — every UI interaction goes through a page-object method. Presence
is asserted with waiting readers; absence with non-waiting probes.
"""
from pytest_bdd import given, when, then, parsers, scenarios

from config.paths import feature_path

scenarios(str(feature_path("shopping_session")))


# ─────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────

@given("a newly registered account is logged in")
def register_and_login(login_page, nav_page, unique_username, base_url):
    """Own the starting state: create a fresh account so the cart begins empty.

    The email is derived from unique_username so the account is unique per run
    on this shared application.
    """
    email = f"{unique_username}@example.com"
    login_page.open_login_page(base_url)
    login_page.start_signup(unique_username, email)
    assert nav_page.wait_until_logged_in(), "New account did not end up logged in"


@given("I am on the signup and login page")
def open_login_page(login_page, base_url):
    login_page.open_login_page(base_url)


@given(parsers.re(r'I am logged in as a "(?P<role>[^"]*)" user'))
def logged_in_as_role(login_page, nav_page, credentials, base_url, role):
    email, password = credentials(role)
    login_page.open_login_page(base_url)
    login_page.login_as(email, password)
    assert nav_page.wait_until_logged_in(), "Expected to be logged in"


# ─────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────

@when("I open the products page")
def open_products(nav_page):
    nav_page.open_products()


@when(parsers.re(r'I search for "(?P<term>[^"]*)"'))
def search_for(products_page, term):
    products_page.search_for(term)


@when(parsers.re(r'I open the product "(?P<product_name>[^"]*)" from the results'))
def open_product(products_page, product_name):
    products_page.open_product(product_name)


@when("I add the product to the cart")
def add_to_cart(product_detail_page):
    product_detail_page.add_to_cart()


@when("I view the cart from the modal")
def view_cart_from_modal(product_detail_page):
    product_detail_page.view_cart_from_modal()


@when(parsers.re(r'I remove the product "(?P<product_name>[^"]*)" from the cart'))
def remove_product(cart_page, product_name):
    cart_page.delete_product(product_name)


@when("I log out")
def log_out(nav_page):
    nav_page.logout()


@when(parsers.re(r'I log in as a "(?P<role>[^"]*)" user with an incorrect password'))
def login_wrong_password(login_page, credentials, role):
    email, _ = credentials(role)
    login_page.login_as(email, "definitely-not-the-password")


@when("I clear the credential fields")
def clear_credentials(login_page):
    login_page.clear_credentials()


@when(parsers.re(r'I log in with email "(?P<email>[^"]*)" and password "(?P<password>[^"]*)"'))
def login_with_literal_credentials(login_page, email, password):
    login_page.login_as(email, password)


# ─────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────

@then("the search results should be shown")
def assert_search_shown(products_page):
    assert products_page.search_executed(), "Search did not appear to execute"


@then(parsers.re(r'I should see the product "(?P<product_name>[^"]*)" in the results'))
def assert_product_in_results(products_page, product_name):
    assert products_page.has_result(product_name), \
        f"Expected {product_name!r} among the search results"


@then(parsers.re(r'the product "(?P<product_name>[^"]*)" should be priced "(?P<price>[^"]*)"'))
def assert_product_priced(products_page, product_name, price):
    row_text = products_page.row_text_for(product_name)
    assert price in row_text, f"Expected price {price!r} in {row_text!r}"


@then(parsers.re(r'I should see the product detail for "(?P<product_name>[^"]*)"'))
def assert_product_detail(product_detail_page, product_name):
    assert product_detail_page.is_loaded(), "Product detail page did not load"
    actual = product_detail_page.product_name()
    assert product_name in actual, f"Expected {product_name!r} in {actual!r}"


@then(parsers.re(r'the cart should contain the product "(?P<product_name>[^"]*)"'))
def assert_cart_contains(cart_page, product_name):
    assert cart_page.has_product(product_name), \
        f"Expected {product_name!r} in the cart"


@then("the cart should be empty")
def assert_cart_empty(cart_page):
    assert cart_page.is_empty(), "Expected the cart to be empty"


@then("I should be logged out")
def assert_logged_out(nav_page):
    assert nav_page.wait_until_logged_out(), "Expected to be logged out"


@then("I should see the login and signup link")
def assert_signup_login_link(nav_page):
    assert nav_page.wait_until_logged_out(), "Expected the login/signup link to be shown"


@then(parsers.re(r'I should see the error message "(?P<expected_message>[^"]*)"'))
def assert_error_message(login_page, expected_message):
    actual = login_page.get_login_error()
    assert expected_message in actual, f"Expected {expected_message!r} in {actual!r}"


@then("I should not be logged in")
def assert_not_logged_in(nav_page):
    assert not nav_page.is_logged_in(), "Unexpectedly logged in"


@then("no product cards should be displayed")
def assert_no_product_cards(products_page):
    assert products_page.get_result_count() == 0, \
        "Expected zero product cards for the no-match search"
