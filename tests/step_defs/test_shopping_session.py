"""Step definitions for features/shopping_session.feature.

Follows the login.py reference style:
- Declares every step its own feature uses (steps are module-scoped).
- Calls page-object methods only; no selectors in step definitions.
- Logs in by ROLE via the `credentials` fixture; invalid data stays literal.
- Asserts PRESENCE with waiting readers and ABSENCE with non-waiting probes.
"""
from pytest_bdd import given, when, then, parsers, scenarios

from config.paths import feature_path

scenarios(str(feature_path("shopping_session")))


# ─────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────

@given("I am on the signup and login page")
def open_login_page(login_page, base_url):
    login_page.open(base_url)


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
    login_page.login_as(email, "WrongPass!123")


@when(parsers.re(r'I log in with email "(?P<email>[^"]*)" and password "(?P<password>[^"]*)"'))
def login_with_literal_credentials(login_page, email, password):
    """Literal values, for unknown-email and empty-field scenarios."""
    login_page.login_as(email, password)


@when("I clear the credential fields")
def clear_credentials(login_page):
    login_page.clear_credentials()


@when("I go to the products page")
def go_to_products_page(nav_page):
    nav_page.open_products()


@when(parsers.re(r'I search for "(?P<term>[^"]*)"'))
def search_for_term(products_page, term):
    products_page.search_for(term)


@when(parsers.re(r'I open the product "(?P<name>[^"]*)" from the results'))
def open_product_from_results(products_page, name):
    products_page.open_product_by_name(name)


@when("I add the product to the cart from the detail page")
def add_product_to_cart(product_detail_page):
    product_detail_page.add_to_cart()
    product_detail_page.wait_for_added_modal()


@when("I view the cart from the modal")
def view_cart_from_modal(product_detail_page):
    product_detail_page.view_cart_from_modal()


@when(parsers.re(r'I remove the product "(?P<name>[^"]*)" from the cart'))
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


@then("I should see the signup and login link in the navigation")
def assert_signup_login_link_shown(nav_page):
    assert nav_page.is_logged_out(), "Expected the Signup/Login link in the navigation"


@then("the search results should be shown")
def assert_search_results_shown(products_page):
    assert products_page.has_searched(), "Expected the searched-products heading"


@then(parsers.re(r'I should see the product "(?P<name>[^"]*)" in the results'))
def assert_product_in_results(products_page, name):
    assert products_page.has_product(name), f"Expected {name!r} in the search results"


@then("no product results should be displayed")
def assert_no_results(products_page):
    assert products_page.get_result_card_count() == 0, "Expected zero product result cards"


@then(parsers.re(r'I should see the product name "(?P<name>[^"]*)" on the product detail page'))
def assert_product_detail_name(product_detail_page, name):
    actual = product_detail_page.product_name()
    assert name in actual, f"Expected {name!r} on the detail page, got {actual!r}"


@then(parsers.re(r'the cart should contain the product "(?P<name>[^"]*)"'))
def assert_cart_contains_product(cart_page, name):
    assert cart_page.has_product(name), f"Expected {name!r} in the cart"


@then(parsers.parse("the cart should have exactly {count:d} item"))
def assert_cart_item_count(cart_page, count):
    actual = cart_page.get_row_count()
    assert actual == count, f"Expected {count} cart item(s), got {actual}"


@then("the cart should be empty")
def assert_cart_empty(cart_page):
    assert cart_page.is_empty(), "Expected the cart to be empty"


@then(parsers.re(r'I should see the error message "(?P<expected_message>[^"]*)"'))
def assert_error_message(login_page, expected_message):
    actual = login_page.get_login_error()
    assert expected_message in actual, f"Expected {expected_message!r} in {actual!r}"


@then("I should remain on the login page")
def assert_still_on_login(login_page):
    assert login_page.is_loaded(), "Expected to stay on the login page"
