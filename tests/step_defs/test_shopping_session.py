"""Step definitions for features/shopping_session.feature.

Binds the shopping-session scenarios to page-object methods only. Selectors
never appear here; each interaction goes through a business-verb method.

Conventions followed (see reference test_login.py):
- Every step phrase the feature uses is declared in THIS file. Steps are
  module-scoped fixtures, so a step declared elsewhere is not visible here.
- Real logins go through the `credentials` fixture by ROLE. Invalid data
  (empty values, wrong passwords, malformed emails) stays literal — it is
  test data, not a secret.
- Quoted values that can be empty use parsers.re with [^"]*; parsers.parse
  cannot match "".
- Presence is asserted with waiting readers; absence with non-waiting probes.
- Cart-state assertions are RELATIVE to the product this test added/removed,
  because the shared `registered` account's cart is not guaranteed empty.
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
    """Literal values, for invalid, malformed and empty-field scenarios."""
    login_page.login_as(email, password)


@when("I clear the credential fields")
def clear_credentials(login_page):
    login_page.clear_credentials()


@when("I go to the products page")
def go_to_products(nav_page, products_page):
    nav_page.go_to_products()
    products_page.confirm_arrival()


@when(parsers.re(r'I search for "(?P<term>[^"]*)"'))
def search_for_term(products_page, term):
    products_page.search_for(term)


@when(parsers.parse('I open the product "{product_name}" from the search results'))
def open_product_from_results(products_page, product_name):
    products_page.open_product(product_name)


@when("I add the product to the cart from the detail page")
def add_to_cart_from_detail(product_detail_page):
    product_detail_page.add_to_cart()


@when("I view the cart from the added-to-cart modal")
def view_cart_from_modal(product_detail_page, cart_page):
    product_detail_page.view_cart_from_modal()
    cart_page.confirm_arrival()


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
    """Non-waiting probe: the absence case is the expected case, so nothing
    may raise. The waiting reader would time out instead of returning False."""
    assert not nav_page.is_logged_in(), "Unexpectedly logged in"


@then("I should see my account name in the navigation")
def assert_account_name_shown(nav_page):
    banner = nav_page.logged_in_name()
    assert "Logged in as" in banner, f"Expected a logged-in banner, got {banner!r}"


@then(parsers.parse('I should see "{product_name}" in the search results'))
def assert_product_in_results(products_page, product_name):
    assert products_page.has_search_executed(), "Search did not appear to execute"
    assert products_page.has_result(product_name), (
        f"Expected {product_name!r} among the search results, "
        f"got {products_page.get_result_names()!r}"
    )


@then(parsers.parse('the product detail page should show the product name "{product_name}"'))
def assert_detail_product_name(product_detail_page, product_name):
    actual = product_detail_page.product_name()
    assert actual == product_name, f"Expected product {product_name!r}, got {actual!r}"


@then(parsers.re(r'the cart should contain "(?P<product_name>[^"]*)" with quantity (?P<quantity>\d+)'))
def assert_cart_contains(cart_page, product_name, quantity):
    """Relative assertion — this product, added by THIS test, is present with
    the expected quantity. Other pre-existing rows are ignored."""
    expected_qty = int(quantity)
    assert cart_page.has_product(product_name), (
        f"Expected {product_name!r} to be in the cart"
    )
    actual_qty = cart_page.quantity_for(product_name)
    assert actual_qty == expected_qty, (
        f"Expected quantity {expected_qty} for {product_name!r}, got {actual_qty}"
    )


@then(parsers.parse('the cart should no longer contain "{product_name}"'))
def assert_cart_removed(cart_page, product_name):
    """Waits for the specific row to disappear rather than snapshotting the
    list. Relative to the product this test removed — other rows may remain."""
    cart_page.wait_removed(product_name)


@then("I should remain on the login page")
def assert_still_on_login(login_page):
    assert login_page.is_loaded(), "Expected to stay on the login page"


@then(parsers.re(r'I should see the error message "(?P<expected_message>[^"]*)"'))
def assert_error_message(login_page, expected_message):
    actual = login_page.get_login_error()
    assert expected_message in actual, f"Expected {expected_message!r} in {actual!r}"


@then("the search should return no result cards")
def assert_no_result_cards(products_page):
    assert products_page.get_result_count() == 0, (
        f"Expected zero result cards, got {products_page.get_result_names()!r}"
    )
