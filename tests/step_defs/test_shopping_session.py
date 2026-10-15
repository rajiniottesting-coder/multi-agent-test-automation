"""Step definitions for features/shopping_session.feature.

Binds the shopping-session scenarios to page-object methods. Every step the
feature file uses is declared here, since pytest-bdd steps are module-scoped.
Page-object methods only — no selectors reach this file. Presence is asserted
with waiting readers, absence with non-waiting probes.
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
    products_page.open_products(base_url)


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
    login_page.login_as(email, "definitely-not-the-password")


@when(parsers.re(r'I log in with email "(?P<email>[^"]*)" and password "(?P<password>[^"]*)"'))
def login_with_literal_credentials(login_page, email, password):
    """Literal values, for invalid and empty-field scenarios."""
    login_page.login_as(email, password)


@when("I clear the credential fields")
def clear_credentials(login_page):
    login_page.clear_credentials()


@when(parsers.re(r'I search the products page for "(?P<term>[^"]*)"'))
def search_products(products_page, term):
    products_page.search_for(term)


@when(parsers.re(r'I view the product "(?P<product_name>[^"]*)"'))
def view_product(products_page, product_name):
    products_page.open_product_details(product_name)


@when("I add the product to the cart from the detail page")
def add_to_cart(product_detail_page):
    product_detail_page.add_to_cart()


@when("I view the cart from the modal")
def view_cart_from_modal(product_detail_page):
    product_detail_page.view_cart()


@when(parsers.re(r'I remove "(?P<product_name>[^"]*)" from the cart'))
def remove_from_cart(cart_page, product_name):
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
    """Non-waiting probe — the waiting reader would time out rather than
    return False, so the assertion would never be reached."""
    assert not nav_page.is_logged_in(), "Unexpectedly logged in"


@then("I should see my account name in the navigation")
def assert_account_name_shown(nav_page):
    banner = nav_page.logged_in_name()
    assert "Logged in as" in banner, f"Expected a logged-in banner, got {banner!r}"


@then("the searched products heading should be shown")
def assert_searched_heading(products_page):
    assert products_page.is_search_results_shown(), "Search did not run"


@then(parsers.re(r'a product card for "(?P<product_name>[^"]*)" should be present in the results'))
def assert_product_card_present(products_page, product_name):
    assert products_page.has_product_card_for(product_name), \
        f"No product card for {product_name!r} in the results"


@then(parsers.re(r'the product detail page should show the name "(?P<product_name>[^"]*)"'))
def assert_detail_name(product_detail_page, product_name):
    actual = product_detail_page.product_name()
    assert product_name in actual, f"Expected name {product_name!r}, got {actual!r}"


@then(parsers.re(r'the product detail page should show the price "(?P<price>[^"]*)"'))
def assert_detail_price(product_detail_page, price):
    actual = product_detail_page.product_price()
    assert price in actual, f"Expected price {price!r}, got {actual!r}"


@then("I should see the added-to-cart confirmation")
def assert_added_modal(product_detail_page):
    assert product_detail_page.has_added_modal(), "No added-to-cart confirmation"


@then(parsers.re(r'a cart row for "(?P<product_name>[^"]*)" should be present'))
def assert_cart_row_present(cart_page, product_name):
    cart_page.wait_for_product(product_name, present=True)


@then(parsers.re(r'a cart row for "(?P<product_name>[^"]*)" should not be present'))
def assert_cart_row_absent(cart_page, product_name):
    cart_page.wait_for_product(product_name, present=False)


@then("I should be redirected to the login page")
def assert_redirected_to_login(login_page):
    assert login_page.is_loaded(), "Expected to be on the login page"


@then(parsers.re(r'I should see the error message "(?P<expected_message>[^"]*)"'))
def assert_error_message(login_page, expected_message):
    actual = login_page.get_login_error()
    assert expected_message in actual, f"Expected {expected_message!r} in {actual!r}"


@then("I should remain on the login page")
def assert_still_on_login(login_page):
    assert login_page.is_loaded(), "Expected to stay on the login page"


@then("no product cards should be present in the results")
def assert_no_product_cards(products_page):
    assert products_page.has_no_product_cards(), \
        "Expected no product cards for the search term"
