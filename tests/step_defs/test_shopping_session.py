"""Step definitions for features/shopping_session.feature.

Binds every Gherkin step to page-object methods only — no selectors, no raw
Playwright calls. Real logins go through the `credentials` fixture; invalid and
empty values stay literal because they are test data, not secrets.

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


@when("I open the products page")
def open_products(nav_page, products_page):
    nav_page.open_products()
    assert products_page.is_loaded(), "Products page did not load"


@when(parsers.parse('I search for "{term}"'))
def search_for(products_page, term):
    products_page.search_for(term)


@when(parsers.parse('I open the product "{product_name}" from the results'))
def open_product_from_results(products_page, product_name):
    products_page.open_product(product_name)


@when("I add the product to the cart")
def add_product_to_cart(product_detail_page):
    product_detail_page.add_to_cart()


@when("I view the cart from the modal")
def view_cart_from_modal(product_detail_page, cart_page):
    product_detail_page.view_cart_from_modal()
    assert cart_page.is_loaded(), "Cart page did not load"


@when(parsers.parse('I remove the product "{product_name}" from the cart'))
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
    """Non-waiting probe; the waiting reader would time out for a genuine
    logged-out state instead of returning False."""
    assert nav_page.wait_until_logged_out(), "Unexpectedly still logged in"


@then("I should see my account name in the navigation")
def assert_account_name_shown(nav_page):
    banner = nav_page.logged_in_name()
    assert "Logged in as" in banner, f"Expected a logged-in banner, got {banner!r}"


@then("I should see the login and signup link in the navigation")
def assert_signup_login_link(nav_page):
    assert not nav_page.is_logged_in(), "Login/Signup link should be present when signed out"


@then("the search results should be shown")
def assert_search_executed(products_page):
    assert products_page.search_has_executed(), "The search did not execute"


@then(parsers.parse('I should see the product "{product_name}" in the results'))
def assert_product_in_results(products_page, product_name):
    assert products_page.has_product(product_name), (
        f"Expected {product_name!r} among the results, got {products_page.result_names()!r}"
    )


@then(parsers.parse('the product "{product_name}" should be priced "{expected_price}" in the results'))
def assert_product_price(products_page, product_name, expected_price):
    actual = products_page.product_price(product_name)
    assert expected_price in actual, (
        f"Expected {product_name!r} priced {expected_price!r}, got {actual!r}"
    )


@then(parsers.parse('I should see the product detail for "{product_name}"'))
def assert_product_detail(product_detail_page, product_name):
    assert product_detail_page.is_loaded(), "Product detail page did not load"
    actual = product_detail_page.product_name()
    assert product_name in actual, (
        f"Expected product detail for {product_name!r}, got {actual!r}"
    )


@then(parsers.parse('the cart should contain the product "{product_name}"'))
def assert_cart_contains(cart_page, product_name):
    cart_page.wait_for_product_row(product_name, present=True)
    assert cart_page.has_product(product_name), (
        f"Expected {product_name!r} in the cart, got {cart_page.product_names()!r}"
    )


@then(parsers.parse('the cart should have exactly {count:d} product'))
def assert_cart_row_count(cart_page, count):
    cart_page.assert_row_count(count)


@then("the cart should be empty")
def assert_cart_empty(cart_page):
    assert cart_page.is_empty(), "Expected the cart to be empty"


@then(parsers.re(r'I should see the error message "(?P<expected_message>[^"]*)"'))
def assert_error_message(login_page, expected_message):
    actual = login_page.get_login_error()
    assert expected_message in actual, f"Expected {expected_message!r} in {actual!r}"


@then("no product cards should be displayed")
def assert_no_product_cards(products_page):
    count = products_page.result_card_count()
    assert count == 0, f"Expected zero result cards, found {count}"
