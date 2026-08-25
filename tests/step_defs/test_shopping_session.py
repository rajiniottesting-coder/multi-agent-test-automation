"""Step definitions for features/shopping_session.feature.

Binds the shopping-session scenarios to the login, nav, home, products,
cart and product-detail page objects.

Conventions (see the reference login step definitions):
- Declare EVERY step this feature uses in this module — steps are module-scoped.
- Call page-object methods only; never a selector.
- Log in by ROLE via the `credentials` fixture; invalid data stays literal.
- Assert PRESENCE with a waiting reader and ABSENCE with a non-waiting probe.
- Cart assertions are RELATIVE (the product this test added/removed), because
  the shared 'registered' account's cart persists across runs.
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
def open_products_page(products_page, base_url):
    products_page.open_listing(base_url)


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
    """Literal values, for invalid and empty-field scenarios."""
    login_page.login_as(email, password)


@when("I clear the credential fields")
def clear_credentials(login_page):
    login_page.clear_credentials()


@when("I go to the products page")
def go_to_products_page(nav_page, products_page):
    nav_page.go_to_products()
    products_page.confirm_arrival()


@when(parsers.re(r'I search for "(?P<term>[^"]*)"'))
def search_for_term(products_page, term):
    products_page.search_for(term)


@when(parsers.parse('I open the product "{product_name}" from the search results'))
def open_product_from_results(products_page, product_name):
    products_page.open_product(product_name)


@when("I add the product to the cart from the detail page")
def add_product_to_cart(product_detail_page):
    product_detail_page.add_product_to_cart()


@when("I view the cart from the added-to-cart modal")
def view_cart_from_modal(product_detail_page, cart_page):
    product_detail_page.view_cart_from_modal()
    cart_page.confirm_arrival()


@when(parsers.parse('I remove "{product_name}" from the cart'))
def remove_product_from_cart(cart_page, product_name):
    cart_page.remove_product(product_name)


@when("I log out")
def log_out(nav_page, login_page):
    nav_page.logout()
    login_page.confirm_arrival()


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


@then(parsers.parse('the search results should include "{product_name}"'))
def assert_search_results_include(products_page, product_name):
    assert products_page.search_results_include(product_name), (
        f"Expected {product_name!r} among the search results"
    )


@then(parsers.parse('the product detail page should show the product name "{product_name}"'))
def assert_detail_product_name(product_detail_page, product_name):
    actual = product_detail_page.product_name()
    assert actual == product_name, f"Expected {product_name!r}, got {actual!r}"


@then(parsers.parse('the cart should contain a row for "{product_name}"'))
def assert_cart_has_row(cart_page, product_name):
    assert cart_page.has_row_for(product_name), (
        f"Expected a cart row for {product_name!r}"
    )


@then(parsers.parse('the cart should not contain a row for "{product_name}"'))
def assert_cart_row_removed(cart_page, product_name):
    cart_page.wait_until_row_removed(product_name)


@then("I should be redirected to the login page")
def assert_on_login_page(login_page):
    assert login_page.is_loaded(), "Expected to be on the login page"


@then(parsers.re(r'I should see the error message "(?P<expected_message>[^"]*)"'))
def assert_error_message(login_page, expected_message):
    actual = login_page.get_login_error()
    assert expected_message in actual, f"Expected {expected_message!r} in {actual!r}"


@then("I should remain on the login page")
def assert_still_on_login(login_page):
    assert login_page.is_loaded(), "Expected to stay on the login page"


@then("the search should return no product cards")
def assert_no_product_cards(products_page):
    assert not products_page.has_any_result_cards(), (
        "Expected zero product cards for a non-matching search"
    )


@then("the search should return the full catalogue of product cards")
def assert_full_catalogue(products_page):
    assert products_page.has_any_result_cards(), (
        "Expected the full catalogue of product cards for an empty search"
    )
