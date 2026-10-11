"""Step definitions for features/shopping_session.feature.

Wires the shopping_session scenarios to page-object methods. Every step the
feature uses is declared here (steps are module-scoped). Step definitions call
page-object methods only — never a selector, never a raw Playwright call.

Presence is asserted with a waiting reader; absence with a non-waiting probe.
Real logins go through the `credentials` fixture resolved by ROLE; the wrong
password used by the negative scenario is literal test data, not a secret.
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
    login_page.login_as(email, "WrongPass123!")


@when("I go to the products page")
def go_to_products(nav_page):
    nav_page.go_to_products()


@when(parsers.parse('I search for "{term}"'))
def search_for_term(products_page, term):
    products_page.search_for(term)


@when(parsers.parse('I open the product "{product_name}"'))
def open_product(products_page, product_name):
    products_page.open_product_details(product_name)


@when("I add the product to the cart")
def add_product_to_cart(product_detail_page):
    product_detail_page.add_to_cart()


@when("I view the cart from the modal")
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


@then("the search should run")
def assert_search_ran(products_page):
    assert products_page.search_ran(), "Expected the search to have executed"


@then("no product result cards should be shown")
def assert_no_result_cards(products_page):
    assert products_page.has_no_product_cards(), "Expected no product result cards"


@then(parsers.re(r'I should see the error message "(?P<expected_message>[^"]*)"'))
def assert_error_message(login_page, expected_message):
    actual = login_page.get_login_error()
    assert expected_message in actual, f"Expected {expected_message!r} in {actual!r}"


@then("I should remain on the login page")
def assert_still_on_login(login_page):
    assert login_page.is_loaded(), "Expected to stay on the login page"


@then(parsers.parse('I should see the product "{product_name}" in the results'))
def assert_product_in_results(products_page, product_name):
    assert products_page.has_product_in_results(product_name), (
        f"Expected product {product_name!r} in the search results"
    )


@then(parsers.parse('I should see the product name "{product_name}" on the detail page'))
def assert_detail_product_name(product_detail_page, product_name):
    actual = product_detail_page.product_name()
    assert product_name in actual, f"Expected {product_name!r} in {actual!r}"


@then(parsers.parse('I should see the product price "{price}" on the detail page'))
def assert_detail_product_price(product_detail_page, price):
    actual = product_detail_page.product_price()
    assert price in actual, f"Expected {price!r} in {actual!r}"


@then("I should see the add to cart confirmation modal")
def assert_added_modal(product_detail_page):
    assert product_detail_page.has_added_modal(), "Expected the add-to-cart modal"


@then(parsers.parse('the cart should contain "{product_name}"'))
def assert_cart_contains(cart_page, product_name):
    assert cart_page.has_product(product_name), (
        f"Expected the cart to contain {product_name!r}"
    )


@then(parsers.parse('"{product_name}" should no longer be in the cart'))
def assert_cart_no_longer_contains(cart_page, product_name):
    cart_page.wait_for_product(product_name, present=False)
