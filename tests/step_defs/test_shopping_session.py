"""Step definitions for features/shopping_session.feature.

Binds the shopping-session feature to page-object methods. Every step the
feature uses is declared here — steps are module-scoped, so a step defined in
another module is not visible in this one.

Conventions (see tests/step_defs/test_login.py):
- Call page-object methods only; never a selector in a step definition.
- parsers.re with [^"]* where a quoted value can be empty; parsers.parse
  cannot match "".
- Log in by ROLE via the `credentials` fixture. Invalid/literal data stays
  literal — it is test data, not a credential.
- Assert PRESENCE with a waiting reader, ABSENCE with a non-waiting probe.
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


@when(parsers.re(r'I search for "(?P<term>[^"]*)"'))
def search_for_term(products_page, term):
    products_page.search_for(term)


@when(parsers.re(r'I open the product "(?P<name>[^"]*)" from the search results'))
def open_product_from_results(products_page, name):
    products_page.open_product(name)


@when("I add the product to the cart from the detail page")
def add_product_to_cart(product_detail_page):
    product_detail_page.add_product_to_cart()


@when("I view the cart from the added-to-cart modal")
def view_cart_from_modal(product_detail_page):
    product_detail_page.view_cart_from_modal()


@when(parsers.re(r'I remove "(?P<name>[^"]*)" from the cart'))
def remove_from_cart(cart_page, name):
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
    """Non-waiting probe: the waiting reader would time out rather than
    return False, so the assertion would never be reached."""
    assert not nav_page.is_logged_in(), "Unexpectedly logged in"


@then("I should see my account name in the navigation")
def assert_account_name_shown(nav_page):
    banner = nav_page.logged_in_name()
    assert "Logged in as" in banner, f"Expected a logged-in banner, got {banner!r}"


@then("I should see the product listing")
def assert_product_listing(products_page):
    assert products_page.is_loaded(), "Expected the product listing to load"


@then(parsers.re(r'the search results should include "(?P<name>[^"]*)"'))
def assert_search_includes(products_page, name):
    assert products_page.search_has_executed(), "Search did not execute"
    names = products_page.get_result_names()
    assert any(name in n for n in names), f"Expected {name!r} in results {names!r}"


@then(parsers.re(r'I should see the product detail for "(?P<name>[^"]*)"'))
def assert_product_detail(product_detail_page, name):
    assert product_detail_page.is_loaded(), "Product detail page did not load"
    actual = product_detail_page.product_name()
    assert name in actual, f"Expected {name!r} in detail name {actual!r}"


@then(parsers.re(r'the cart should contain a row for "(?P<name>[^"]*)"'))
def assert_cart_contains(cart_page, name):
    cart_page.wait_for_product_row(name, present=True)


@then(parsers.re(r'the cart should not contain a row for "(?P<name>[^"]*)"'))
def assert_cart_not_contains(cart_page, name):
    cart_page.wait_for_product_row(name, present=False)


@then("I should remain on the login page")
def assert_still_on_login(login_page):
    assert login_page.is_loaded(), "Expected to stay on the login page"


@then(parsers.re(r'I should see the error message "(?P<expected_message>[^"]*)"'))
def assert_error_message(login_page, expected_message):
    actual = login_page.get_login_error()
    assert expected_message in actual, f"Expected {expected_message!r} in {actual!r}"


@then("the search should return no product cards")
def assert_no_product_cards(products_page):
    assert products_page.has_no_results(), "Expected zero product cards"


@then("the search should return the full catalogue")
def assert_full_catalogue(products_page):
    assert products_page.has_results(), "Expected the full catalogue of products"
