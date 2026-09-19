"""Step definitions for features/shopping_session.feature.

Binds the shopping-session steps to page-object methods. Selectors never
appear here — the step definitions call named page-object methods only.

- Real logins go through a ROLE resolved by the `credentials` fixture.
  Invalid data (wrong email/password) stays literal, as it is test data.
- Presence is asserted with waiting readers; absence with non-waiting probes
  or waiting-for-absence helpers, never by negating a waiting probe.
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
def go_to_products(products_page, base_url):
    products_page.open_products(base_url)


@when(parsers.re(r'I search for "(?P<term>[^"]*)"'))
def search_for_term(products_page, term):
    products_page.search_for(term)


@when(parsers.re(r'I view the product "(?P<name>[^"]*)"'))
def view_product(products_page, name):
    products_page.view_product(name)


@when("I add the product to the cart")
def add_product_to_cart(product_detail_page):
    product_detail_page.add_to_cart()


@when("I view the cart from the modal")
def view_cart_from_modal(product_detail_page):
    product_detail_page.view_cart_from_modal()


@when(parsers.re(r'I remove the product "(?P<name>[^"]*)" from the cart'))
def remove_product_from_cart(cart_page, name):
    cart_page.remove_product(name)


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
    """Non-waiting probe. The waiting reader would time out rather than
    return False, so the assertion would never be reached."""
    assert not nav_page.is_logged_in(), "Unexpectedly logged in"


@then("I should see my account name in the navigation")
def assert_account_name_shown(nav_page):
    banner = nav_page.logged_in_name()
    assert "Logged in as" in banner, f"Expected a logged-in banner, got {banner!r}"


@then("the searched products heading should be shown")
def assert_searched_products_heading(products_page):
    assert products_page.is_search_executed(), "Searched Products heading not shown"


@then(parsers.re(r'the search results should contain "(?P<name>[^"]*)"'))
def assert_search_results_contain(products_page, name):
    names = products_page.get_result_names()
    assert any(name in n for n in names), f"Expected {name!r} in {names!r}"


@then(parsers.re(r'the product name should be "(?P<name>[^"]*)"'))
def assert_product_name(product_detail_page, name):
    actual = product_detail_page.product_name()
    assert actual == name, f"Expected product name {name!r}, got {actual!r}"


@then(parsers.re(r'the product price should contain "(?P<value>[^"]*)"'))
def assert_product_price_contains(product_detail_page, value):
    price = product_detail_page.product_price()
    assert value in price, f"Expected {value!r} in price {price!r}"


@then(parsers.re(r'the cart should contain the product "(?P<name>[^"]*)"'))
def assert_cart_contains(cart_page, name):
    cart_page.wait_until_contains(name)


@then(parsers.re(r'the cart should no longer contain the product "(?P<name>[^"]*)"'))
def assert_cart_absent(cart_page, name):
    cart_page.wait_until_absent(name)


@then(parsers.re(r'I should see the error message "(?P<expected_message>[^"]*)"'))
def assert_error_message(login_page, expected_message):
    actual = login_page.get_login_error()
    assert expected_message in actual, f"Expected {expected_message!r} in {actual!r}"


@then("I should remain on the login page")
def assert_still_on_login(login_page):
    assert login_page.is_loaded(), "Expected to stay on the login page"


@then("no product result cards should be displayed")
def assert_no_result_cards(products_page):
    count = products_page.get_result_card_count()
    assert count == 0, f"Expected zero result cards, found {count}"
