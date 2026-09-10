"""Step definitions for features/shopping_session.feature.

Covers the end-to-end shopping session (login, search, add-to-cart, remove,
logout), the anonymous-cart-carryover edge case, the nonexistent-search edge
case, and the negative login scenarios.

Conventions (see reference test_login.py):
  - real logins go through the `credentials` fixture keyed by ROLE
  - invalid / empty / malformed credentials stay literal — they are test data
  - step defs call page-object methods only, never selectors
  - presence is asserted with waiting readers, absence with non-waiting probes
"""
from pytest_bdd import given, when, then, parsers, scenarios

from config.paths import feature_path

scenarios(str(feature_path("shopping_session")))


# ─────────────────────────────────────────────────────────────
# Given / When — session & navigation
# ─────────────────────────────────────────────────────────────

@given("I am on the signup and login page")
@when("I am on the signup and login page")
def open_login_page(login_page, base_url):
    login_page.open_login_page(base_url)


@when(parsers.re(r'I log in as a "(?P<role>[^"]*)" user'))
def login_as_role(login_page, credentials, role):
    """Log in with real credentials resolved from the environment by role."""
    email, password = credentials(role)
    login_page.login_as(email, password)


@when(parsers.re(r'I log in with email "(?P<email>[^"]*)" and password "(?P<password>[^"]*)"'))
def login_with_literal_credentials(login_page, email, password):
    """Literal values, for invalid, empty and malformed credential scenarios."""
    login_page.login_as(email, password)


@when("I clear the credential fields")
def clear_credentials(login_page):
    login_page.clear_credentials()


@when("I go to the products page")
def go_to_products(products_page, base_url):
    products_page.open_listing(base_url)


@when("I log out")
def logout(nav_page):
    nav_page.logout()


# ─────────────────────────────────────────────────────────────
# When — product search & detail
# ─────────────────────────────────────────────────────────────

@when(parsers.re(r'I search for the product "(?P<name>[^"]*)"'))
def search_for_product(products_page, name):
    products_page.search_for(name)


@when(parsers.re(r'I open the product "(?P<name>[^"]*)" from the search results'))
def open_product(products_page, name):
    products_page.open_product(name)


@when("I add the displayed product to the cart")
def add_displayed_product(product_detail_page):
    product_detail_page.add_displayed_product_to_cart()


@when("I view the cart from the add-to-cart modal")
def view_cart_from_modal(product_detail_page):
    product_detail_page.view_cart_from_modal()


@when("I continue shopping from the add-to-cart modal")
def continue_shopping_from_modal(product_detail_page):
    product_detail_page.continue_shopping_from_modal()


# ─────────────────────────────────────────────────────────────
# When — cart
# ─────────────────────────────────────────────────────────────

@when("I view the cart")
def view_cart(cart_page, base_url):
    cart_page.view_cart(base_url)


@when(parsers.re(r'I remove the product "(?P<name>[^"]*)" from the cart'))
def remove_product(cart_page, name):
    cart_page.remove_product(name)


# ─────────────────────────────────────────────────────────────
# Then — session state
# ─────────────────────────────────────────────────────────────

@then("I should be logged in")
def assert_logged_in(nav_page):
    assert nav_page.wait_until_logged_in(), "No session after logging in"


@then("I should not be logged in")
@given("I should not be logged in")
def assert_not_logged_in(nav_page):
    """Non-waiting probe. The waiting reader would time out rather than
    return False, so the assertion would never be reached."""
    assert not nav_page.is_logged_in(), "Unexpectedly logged in"


@then("I should see my account name in the navigation")
def assert_account_name_shown(nav_page):
    banner = nav_page.logged_in_name()
    assert "Logged in as" in banner, f"Expected a logged-in banner, got {banner!r}"


@then(parsers.re(r'I should see the error message "(?P<expected_message>[^"]*)"'))
def assert_error_message(login_page, expected_message):
    actual = login_page.get_login_error()
    assert expected_message in actual, f"Expected {expected_message!r} in {actual!r}"


# ─────────────────────────────────────────────────────────────
# Then — search results
# ─────────────────────────────────────────────────────────────

@then(parsers.re(r'the search results should include the product "(?P<name>[^"]*)"'))
def assert_search_includes(products_page, name):
    assert products_page.has_result(name), f"Expected {name!r} in the search results"


@then("the search should return no product result cards")
def assert_no_results(products_page):
    assert products_page.get_result_card_count() == 0, \
        "Expected zero product result cards for the nonexistent search term"


# ─────────────────────────────────────────────────────────────
# Then — product detail
# ─────────────────────────────────────────────────────────────

@then(parsers.re(r'the product detail page should show the product name "(?P<name>[^"]*)"'))
def assert_detail_name(product_detail_page, name):
    actual = product_detail_page.product_name()
    assert name in actual, f"Expected product name {name!r}, got {actual!r}"


# ─────────────────────────────────────────────────────────────
# Then — cart contents
# ─────────────────────────────────────────────────────────────

@then(parsers.re(r'the cart should contain the product "(?P<name>[^"]*)"'))
def assert_cart_contains(cart_page, name):
    cart_page.wait_until_contains(name)


@then(parsers.re(r'the cart should no longer contain the product "(?P<name>[^"]*)"'))
def assert_cart_absent(cart_page, name):
    cart_page.wait_until_absent(name)
