"""Step definitions for features/shopping_session.feature.

Binds the shopping-session feature to page-object methods. Every step the
feature uses is declared here — steps are module-scoped, so a step defined in
another module is not visible to this one.

Rules applied:
- Call page-object methods only; no selectors in step definitions.
- Log in by ROLE via the `credentials` fixture; invalid data stays literal.
- Assert PRESENCE with a waiting reader, ABSENCE with a non-waiting probe.
- Empty quoted values use parsers.re with [^"]* placeholders.
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


@when("I go to the products page")
def go_to_products_page(products_page, base_url):
    products_page.open_products(base_url)


@when(parsers.parse('I search for "{term}"'))
def search_for_term(products_page, term):
    products_page.search_for(term)


@when(parsers.parse('I open the product "{product_name}" from the results'))
def open_product_from_results(products_page, product_name):
    products_page.open_product(product_name)


@when("I add the product to the cart")
def add_product_to_cart(product_detail_page):
    product_detail_page.add_product_to_cart()


@when("I view the cart from the added-to-cart modal")
def view_cart_from_modal(product_detail_page):
    product_detail_page.view_cart_from_modal()


@when(parsers.parse('I remove "{product_name}" from the cart'))
def remove_product_from_cart(cart_page, product_name):
    cart_page.remove_product(product_name)


@when("I log out")
def log_out(nav_page):
    nav_page.logout()


@when("I submit an empty search")
def submit_empty_search(products_page):
    products_page.submit_empty_search()


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


@then(parsers.parse('I should see the product "{product_name}" in the results'))
def assert_product_in_results(products_page, product_name):
    assert products_page.has_product(product_name), (
        f"Expected product {product_name!r} in the results"
    )


@then(parsers.parse('I should see the product name "{product_name}" on the detail page'))
def assert_product_name_on_detail(product_detail_page, product_name):
    actual = product_detail_page.product_name()
    assert product_name in actual, f"Expected {product_name!r} in {actual!r}"


@then(parsers.parse('the cart should contain a row for "{product_name}"'))
def assert_cart_has_row(cart_page, product_name):
    assert cart_page.has_product_row(product_name), (
        f"Expected a cart row for {product_name!r}"
    )


@then(parsers.parse('the cart should no longer contain a row for "{product_name}"'))
def assert_cart_row_removed(cart_page, product_name):
    cart_page.wait_until_product_removed(product_name)


@then("I should be redirected to the login page")
def assert_on_login_page(login_page):
    assert login_page.is_loaded(), "Expected to be redirected to the login page"


@then("I should remain on the login page")
def assert_still_on_login(login_page):
    assert login_page.is_loaded(), "Expected to stay on the login page"


@then(parsers.re(r'I should see the error message "(?P<expected_message>[^"]*)"'))
def assert_error_message(login_page, expected_message):
    actual = login_page.get_login_error()
    assert expected_message in actual, f"Expected {expected_message!r} in {actual!r}"


@then("the full product catalogue should still be shown")
def assert_full_catalogue_shown(products_page):
    assert products_page.has_full_catalogue(), (
        "Expected the full product catalogue to still be shown"
    )


@then("no product cards should be shown")
def assert_no_product_cards(products_page):
    assert products_page.has_no_product_cards(), "Expected zero product cards"
