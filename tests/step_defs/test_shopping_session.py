"""Step definitions for features/shopping_session.feature.

Binds the shopping-session feature to page objects only — no selectors here.
Real logins go through the `credentials` fixture; invalid credentials stay
literal because they are test data, not secrets. Presence is asserted with
waiting readers, absence with non-waiting probes.

The logout link is a NavPage concern: NavPage exposes `logout()` for the
action and `is_logged_in()` / `wait_until_logged_in()` / `logged_in_name()`
for the readers.
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
def empty_the_cart(cart_page, base_url):
    """Own the starting state so an absolute empty assertion is honest."""
    cart_page.open_cart(base_url)
    cart_page.empty_the_cart()


@given("I am on the products page")
def open_products_page(products_page, base_url):
    products_page.open_listing(base_url)


# ─────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────

@when(parsers.re(r'I log in as a "(?P<role>[^"]*)" user$'))
def login_as_role(login_page, credentials, role):
    email, password = credentials(role)
    login_page.login_as(email, password)


@when(parsers.re(r'I log in with email "(?P<email>[^"]*)" and password "(?P<password>[^"]*)"'))
def login_with_literal_credentials(login_page, email, password):
    """Literal values, for the invalid-credentials scenario."""
    login_page.login_as(email, password)


@when("I open the products page")
def when_open_products_page(products_page, base_url):
    products_page.open_listing(base_url)


@when(parsers.parse('I search for "{term}"'))
def search_for(products_page, term):
    products_page.search_for(term)


@when(parsers.parse('I open the product "{product_name}" from the search results'))
def open_product_from_results(products_page, product_name):
    products_page.open_product(product_name)


@when("I add the product to the cart")
def add_product_to_cart(product_detail_page):
    product_detail_page.add_product_to_cart()


@when("I go to the cart from the add-to-cart modal")
def go_to_cart_from_modal(product_detail_page):
    product_detail_page.go_to_cart_from_modal()


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
    """Non-waiting probe: the waiting reader would time out for absence."""
    assert not nav_page.is_logged_in(), "Unexpectedly logged in"


@then("I should see my account name in the navigation")
def assert_account_name_shown(nav_page):
    banner = nav_page.logged_in_name()
    assert "Logged in as" in banner, f"Expected a logged-in banner, got {banner!r}"


@then("I should see the searched products results")
def assert_search_executed(products_page):
    assert products_page.is_search_executed(), "Search did not execute"


@then(parsers.parse('the product detail page should show the product name "{product_name}"'))
def assert_detail_product_name(product_detail_page, product_name):
    actual = product_detail_page.get_product_name()
    assert product_name in actual, f"Expected {product_name!r} in {actual!r}"


@then(parsers.parse('the cart should contain the product "{product_name}"'))
def assert_cart_contains_product(cart_page, product_name):
    cart_page.wait_for_product(product_name, present=True)


@then("the cart should be empty")
def assert_cart_empty(cart_page):
    assert cart_page.is_empty(), "Expected the cart to be empty"


@then(parsers.re(r'I should see the error message "(?P<expected_message>[^"]*)"'))
def assert_error_message(login_page, expected_message):
    actual = login_page.get_login_error()
    assert expected_message in actual, f"Expected {expected_message!r} in {actual!r}"


@then("no product result cards should be displayed")
def assert_no_result_cards(products_page):
    count = products_page.get_result_card_count()
    assert count == 0, f"Expected zero result cards, found {count}"
