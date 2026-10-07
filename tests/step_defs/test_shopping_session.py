"""Step definitions for features/shopping_session.feature.

Binds the shopping-session scenarios to page-object methods. Every step the
feature uses is declared here, because pytest-bdd steps are module-scoped.
Page-object fixtures (login_page, nav_page, products_page, product_detail_page,
cart_page) come from tests/step_defs/conftest.py.

Conventions copied from the reference login step definitions:
  - call page-object methods only; never a selector in a step def
  - real logins go through a ROLE via the `credentials` fixture
  - invalid / literal data stays literal — it is test data, not a secret
  - PRESENCE asserted with a waiting reader, ABSENCE with a non-waiting probe
  - parsers.re with [^"]* wherever a quoted value could be empty
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
    """Literal values, for the non-existent-email scenario."""
    login_page.login_as(email, password)


@when("I clear the credential fields")
def clear_credentials(login_page):
    login_page.clear_credentials()


@when("I go to the products page")
def go_to_products(products_page, base_url):
    products_page.open_listing(base_url)


@when(parsers.re(r'I search for "(?P<term>[^"]*)"'))
def search_for_product(products_page, term):
    products_page.search_for(term)


@when(parsers.re(r'I view the product "(?P<name>[^"]*)"'))
def view_product(products_page, name):
    products_page.open_product(name)


@when("I add the product to the cart")
def add_product_to_cart(product_detail_page):
    product_detail_page.add_to_cart()


@when("I view the cart from the modal")
def view_cart_from_modal(product_detail_page):
    product_detail_page.view_cart_from_modal()


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
    """The Logout link is rendered only while authenticated."""
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


@then(parsers.re(r'I should see a product card for "(?P<name>[^"]*)"'))
def assert_product_card_present(products_page, name):
    assert products_page.has_product_card(name), f"No product card for {name!r}"


@then(parsers.re(r'the product name should be "(?P<name>[^"]*)"'))
def assert_product_name(product_detail_page, name):
    actual = product_detail_page.product_name()
    assert actual == name, f"Expected product name {name!r}, got {actual!r}"


@then(parsers.re(r'the product price should contain "(?P<value>[^"]*)"'))
def assert_product_price_contains(product_detail_page, value):
    actual = product_detail_page.product_price()
    assert value in actual, f"Expected {value!r} in price {actual!r}"


@then(parsers.re(r'the cart should contain a row for "(?P<product_name>[^"]*)"'))
def assert_cart_has_row(cart_page, product_name):
    assert cart_page.has_product_row(product_name), f"No cart row for {product_name!r}"


@then(parsers.re(r'the cart should no longer contain "(?P<product_name>[^"]*)"'))
def assert_cart_row_removed(cart_page, product_name):
    """Waits for the named row to disappear — relative to this test's own
    addition, not an absolute empty-cart claim."""
    cart_page.wait_until_product_removed(product_name)


@then("I should remain on the login page")
def assert_still_on_login(login_page):
    assert login_page.is_loaded(), "Expected to stay on the login page"


@then(parsers.re(r'I should see the error message "(?P<expected_message>[^"]*)"'))
def assert_error_message(login_page, expected_message):
    actual = login_page.get_login_error()
    assert expected_message in actual, f"Expected {expected_message!r} in {actual!r}"


@then("no product result cards should be displayed")
def assert_no_result_cards(products_page):
    count = products_page.get_result_card_count()
    assert count == 0, f"Expected zero result cards, found {count}"
