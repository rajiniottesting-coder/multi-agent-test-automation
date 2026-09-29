"""Step definitions for features/shopping_session.feature.

Binds every Gherkin step to a page-object method. Selectors never appear here;
step definitions call named page-object methods only. Presence is asserted with
waiting readers, absence with non-waiting probes. Real logins go through the
`credentials` fixture by ROLE; invalid data stays literal.
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


@when(parsers.re(r'I log in with email "(?P<email>[^"]*)" and password "(?P<password>[^"]*)"'))
def login_with_literal_credentials(login_page, email, password):
    """Literal values, for the unregistered-email scenario."""
    login_page.login_as(email, password)


@when("I dismiss the login error")
def dismiss_login_error(login_page, base_url):
    """Clear residual error state between repeated login attempts by reloading
    the login page, so the next attempt's assertion reads a fresh response."""
    login_page.open_login_page(base_url)


@when(parsers.re(r'I search for the product "(?P<term>[^"]*)"'))
def search_for_product(products_page, base_url, term):
    products_page.open_listing(base_url)
    products_page.search_for(term)


@when(parsers.re(r'I open the product "(?P<name>[^"]*)" from the search results'))
def open_product_from_results(products_page, name):
    products_page.open_product(name)


@when("I add the product to the cart from the product detail page")
def add_product_to_cart(product_detail_page):
    product_detail_page.add_to_cart()


@when("I view the cart from the confirmation modal")
def view_cart_from_modal(product_detail_page):
    product_detail_page.view_cart_from_modal()


@when(parsers.re(r'I remove "(?P<name>[^"]*)" from the cart'))
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
    """Non-waiting probe: the waiting reader would time out rather than return
    False, so the assertion would never be reached."""
    assert not nav_page.is_logged_in(), "Unexpectedly logged in"


@then("I should see my account name in the navigation")
def assert_account_name_shown(nav_page):
    banner = nav_page.logged_in_name()
    assert "Logged in as" in banner, f"Expected a logged-in banner, got {banner!r}"


@then(parsers.re(r'I should see a search result for "(?P<name>[^"]*)"'))
def assert_search_result(products_page, name):
    assert products_page.has_search_result_for(name), \
        f"Expected a search result card for {name!r}"


@then(parsers.re(r'I should see the product detail for "(?P<name>[^"]*)"'))
def assert_product_detail(product_detail_page, name):
    actual = product_detail_page.product_name()
    assert name in actual, f"Expected product detail for {name!r}, got {actual!r}"


@then(parsers.re(r'I should see the product price "(?P<price>[^"]*)"'))
def assert_product_price(product_detail_page, price):
    actual = product_detail_page.product_price()
    assert price in actual, f"Expected price {price!r}, got {actual!r}"


@then("I should see the product added confirmation")
def assert_added_confirmation(product_detail_page):
    assert product_detail_page.has_added_confirmation(), \
        "Expected the add-to-cart confirmation modal"


@then(parsers.re(r'the cart should contain a row for "(?P<name>[^"]*)"'))
def assert_cart_has_row(cart_page, name):
    cart_page.wait_for_product_row(name, present=True)


@then(parsers.re(r'the cart should not contain a row for "(?P<name>[^"]*)"'))
def assert_cart_missing_row(cart_page, name):
    cart_page.wait_for_product_row(name, present=False)


@then(parsers.re(r'I should see the error message "(?P<expected_message>[^"]*)"'))
def assert_error_message(login_page, expected_message):
    actual = login_page.get_login_error()
    assert expected_message in actual, f"Expected {expected_message!r} in {actual!r}"


@then("I should remain on the login page")
def assert_still_on_login(login_page):
    assert login_page.is_loaded(), "Expected to stay on the login page"


@then("the search results should show no product cards")
def assert_no_product_cards(products_page):
    assert products_page.get_result_count() == 0, \
        "Expected no product cards for a nonexistent search term"
