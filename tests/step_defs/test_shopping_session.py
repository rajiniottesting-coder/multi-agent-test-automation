"""Step definitions for features/shopping_session.feature.

Bindings for the end-to-end shopping session (SCRUM-181), the negative-login
variants (SCRUM-182) and the nonexistent-search edge case (SCRUM-183).

Conventions copied from tests/step_defs/test_login.py:
  - Every step the feature uses is declared here (steps are module-scoped).
  - Step defs call page-object methods only; no selectors live here.
  - Real logins go through the `credentials` fixture by ROLE; invalid data
    (empty fields, wrong passwords, malformed emails) stays literal.
  - Presence is asserted with a waiting reader, absence with a non-waiting probe.
  - parsers.re with [^"]* is used wherever a quoted value can be empty.
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


@when(parsers.re(r'I log in as a "(?P<role>[^"]*)" user with an incorrect password'))
def login_as_role_wrong_password(login_page, credentials, role):
    """Valid email, deliberately wrong password (test data, not a secret)."""
    email, _ = credentials(role)
    login_page.login_as(email, "WrongPass123!")


@when(parsers.re(r'I log in with email "(?P<email>[^"]*)" and password "(?P<password>[^"]*)"'))
def login_with_literal_credentials(login_page, email, password):
    """Literal values, for the empty-field and malformed-email scenarios."""
    login_page.login_as(email, password)


@when("I clear the credential fields")
def clear_credentials(login_page):
    login_page.clear_credentials()


@when("I go to the products page")
def go_to_products(nav_page):
    nav_page.go_to_products()


@when(parsers.re(r'I search for "(?P<term>[^"]*)"'))
def search_for(products_page, term):
    products_page.search_for(term)


@when(parsers.re(r'I view the product "(?P<name>[^"]*)"'))
def view_product(products_page, name):
    products_page.view_product(name)


@when("I add the displayed product to the cart")
def add_to_cart(product_detail_page):
    product_detail_page.add_to_cart()


@when("I view the cart from the confirmation")
def view_cart_from_modal(product_detail_page):
    product_detail_page.view_cart_from_modal()


@when(parsers.re(r'I remove "(?P<name>[^"]*)" from the cart'))
def remove_from_cart(cart_page, name):
    cart_page.remove_product(name)


@when("I log out")
def logout(nav_page):
    nav_page.logout()


# ─────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────

@then("I should be logged in")
def assert_logged_in(nav_page):
    assert nav_page.wait_until_logged_in(), "No session after logging in"


@then("I should not be logged in")
def assert_not_logged_in(nav_page):
    """Non-waiting probe: the waiting reader would time out instead of
    returning False, so the assertion would never be reached."""
    assert not nav_page.is_logged_in(), "Unexpectedly logged in"


@then("I should see my account name in the navigation")
def assert_account_name_shown(nav_page):
    banner = nav_page.logged_in_name()
    assert "Logged in as" in banner, f"Expected a logged-in banner, got {banner!r}"


@then("the all products listing should be displayed")
def assert_all_products_listing(products_page):
    assert products_page.is_loaded(), "All Products listing was not displayed"


@then("the searched products heading should be displayed")
def assert_searched_products_heading(products_page):
    assert products_page.is_search_results_shown(), \
        "Searched Products heading was not displayed"


@then(parsers.re(r'the search results should include "(?P<name>[^"]*)"'))
def assert_search_results_include(products_page, name):
    assert products_page.has_product(name), \
        f"Expected {name!r} in the search results"


@then(parsers.re(r'the product detail page should show the name "(?P<name>[^"]*)"'))
def assert_product_detail_name(product_detail_page, name):
    actual = product_detail_page.product_name()
    assert actual == name, f"Expected product name {name!r}, got {actual!r}"


@then("the added to cart confirmation should be displayed")
def assert_added_modal(product_detail_page):
    assert product_detail_page.is_added_modal_shown(), \
        "Added-to-cart confirmation modal was not displayed"


@then(parsers.re(r'the cart should contain a row for "(?P<name>[^"]*)"'))
def assert_cart_has_row(cart_page, name):
    assert cart_page.has_product(name), \
        f"Expected a cart row for {name!r}"


@then(parsers.re(r'"(?P<name>[^"]*)" should no longer be in the cart'))
def assert_product_removed(cart_page, name):
    """Relative assertion: the product this scenario added is gone. Other rows
    the shared account may already hold are not evaluated."""
    assert cart_page.is_product_removed(name), \
        f"Expected {name!r} to be gone from the cart"


@then("I should be on the login page")
def assert_on_login_page(login_page):
    assert login_page.is_loaded(), "Expected to be on the login page"


@then("I should remain on the login page")
def assert_remain_on_login_page(login_page):
    assert login_page.is_loaded(), "Expected to stay on the login page"


@then(parsers.re(r'I should see the error message "(?P<expected_message>[^"]*)"'))
def assert_error_message(login_page, expected_message):
    actual = login_page.get_login_error()
    assert expected_message in actual, f"Expected {expected_message!r} in {actual!r}"


@then("no product result cards should be rendered")
def assert_no_result_cards(products_page):
    count = products_page.get_result_count()
    assert count == 0, f"Expected zero result cards, found {count}"
