"""Step definitions for features/shopping_session.feature.

Binds the shopping-session steps to page-object methods. Every phrase the
feature file uses is declared here, since pytest-bdd steps are module-scoped.

Cart assertions are RELATIVE (presence/absence of the product this test
added/removed): the shared 'registered' account's cart persists across runs,
so an absolute count would inherit whatever a previous run left behind.
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

@when(parsers.re(r'I log in as a "(?P<role>[^"]*)" user'))
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
def go_to_products_page(products_page, base_url):
    products_page.open_listing(base_url)


@when(parsers.re(r'I search for the product "(?P<term>[^"]*)"'))
def search_for_product(products_page, term):
    products_page.search_for(term)


@when(parsers.parse('I open the product "{name}" from the results'))
def open_product_from_results(products_page, name):
    products_page.open_product(name)


@when("I add the displayed product to the cart")
def add_displayed_product(product_detail_page):
    product_detail_page.add_displayed_product_to_cart()


@when("I view the cart from the added-to-cart modal")
def view_cart_from_modal(product_detail_page):
    product_detail_page.view_cart_from_modal()


@when(parsers.parse('I remove the product "{name}" from the cart'))
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
    assert not nav_page.is_logged_in(), "Unexpectedly logged in"


@then("I should see my account name in the navigation")
def assert_account_name_shown(nav_page):
    banner = nav_page.logged_in_name()
    assert "Logged in as" in banner, f"Expected a logged-in banner, got {banner!r}"


@then("I should see the login and signup link")
def assert_login_link_shown(nav_page):
    assert nav_page.wait_until_logged_out(), "Expected the login/signup link to be shown"


@then(parsers.parse('the search results should include the product "{name}"'))
def assert_search_includes(products_page, name):
    assert products_page.has_result(name), f"Expected {name!r} in the search results"


@then("the search results should contain no product cards")
def assert_no_result_cards(products_page):
    assert products_page.has_no_result_cards(), "Expected zero product cards"


@then("the search results should contain product cards")
def assert_has_result_cards(products_page):
    assert products_page.has_result_cards(), "Expected product cards in the results"


@then(parsers.parse('the product detail page should show the product name "{name}"'))
def assert_detail_product_name(product_detail_page, name):
    actual = product_detail_page.get_product_name()
    assert name in actual, f"Expected {name!r} on the detail page, got {actual!r}"


@then(parsers.parse('the cart should contain a row for the product "{name}"'))
def assert_cart_contains(cart_page, name):
    assert cart_page.has_product(name), f"Expected a cart row for {name!r}"


@then(parsers.parse('the cart should not contain a row for the product "{name}"'))
def assert_cart_absent(cart_page, name):
    cart_page.assert_product_absent(name)


@then(parsers.re(r'I should see the error message "(?P<expected_message>[^"]*)"'))
def assert_error_message(login_page, expected_message):
    actual = login_page.get_login_error()
    assert expected_message in actual, f"Expected {expected_message!r} in {actual!r}"


@then("I should remain on the login page")
def assert_still_on_login(login_page):
    assert login_page.is_loaded(), "Expected to stay on the login page"
