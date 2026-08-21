"""Step definitions for features/shopping_session.feature.

Binds the shopping-session scenarios to page-object calls. Every step the
feature uses is declared here — pytest-bdd steps are module-scoped, so a step
defined elsewhere is invisible to this module.

Conventions (mirrors tests/step_defs/test_login.py):
- Call page-object methods only; no selectors in step defs.
- Log in by ROLE via the `credentials` fixture. Invalid/empty data stays
  literal — it is test data, not a secret.
- Empty quoted values use parsers.re with [^"]*; parsers.parse cannot match "".
- Presence assertions use waiting readers; absence uses non-waiting probes.
"""
from pytest_bdd import given, when, then, parsers, scenarios

from config.paths import feature_path

scenarios(str(feature_path("shopping_session")))


# ─────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────

@given("a newly registered account")
def newly_registered_account(login_page, base_url, unique_username):
    """Own the starting state: register a fresh account so cart/session state
    starts genuinely empty. The signup flow lands the user on a fuller form;
    for this suite we only need the account to exist and be usable for login.
    """
    email = f"{unique_username}@example.com"
    login_page.open_login_page(base_url)
    login_page.start_signup(unique_username, email)


@given("I am on the signup and login page")
def open_login_page(login_page, base_url):
    login_page.open_login_page(base_url)


# ─────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────

@when(parsers.re(r'I log in as a "(?P<role>[^"]*)" user$'))
def login_as_role(login_page, credentials, role):
    email, password = credentials(role)
    login_page.login_as(email, password)


@when(parsers.re(r'I log in as a "(?P<role>[^"]*)" user with an incorrect password'))
def login_as_role_wrong_password(login_page, credentials, role):
    email, _ = credentials(role)
    login_page.login_as(email, "WrongPass!123")


@when(parsers.re(r'I log in with email "(?P<email>[^"]*)" and password "(?P<password>[^"]*)"'))
def login_with_literal_credentials(login_page, email, password):
    login_page.login_as(email, password)


@when("I clear the credential fields")
def clear_credentials(login_page):
    login_page.clear_credentials()


@when("I open the products page from the navigation")
def open_products_from_nav(nav_page):
    nav_page.open_products()


@when(parsers.parse('I search for "{term}"'))
def search_for_term(products_page, term):
    products_page.search_for(term)


@when(parsers.parse('I open the product "{name}" from the results'))
def open_product_from_results(products_page, name):
    products_page.open_product(name)


@when("I add the product to the cart from the detail page")
def add_product_to_cart(product_detail_page):
    product_detail_page.add_to_cart()


@when("I view the cart from the modal")
def view_cart_from_modal(product_detail_page):
    product_detail_page.view_cart_from_modal()


@when(parsers.parse('I remove "{name}" from the cart'))
def remove_product_from_cart(cart_page, name):
    cart_page.remove_product(name)


@when("I log out from the navigation")
def logout_from_nav(nav_page):
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


@then(parsers.parse('the search results should contain "{name}"'))
def assert_search_contains(products_page, name):
    assert products_page.has_product(name), f"Expected {name!r} in the results"


@then(parsers.parse('I should see the product name "{name}"'))
def assert_product_name(product_detail_page, name):
    actual = product_detail_page.product_name()
    assert name in actual, f"Expected product name {name!r}, got {actual!r}"


@then(parsers.parse('the cart should contain "{name}"'))
def assert_cart_contains(cart_page, name):
    cart_page.wait_for_product_row(name, present=True)


@then(parsers.parse('the cart should have exactly {count:d} item'))
def assert_cart_count(cart_page, count):
    cart_page.assert_row_count(count)


@then("the cart should be empty")
def assert_cart_empty(cart_page):
    assert cart_page.is_empty(), "Expected the cart to be empty"


@then("I should remain on the login page")
def assert_still_on_login(login_page):
    assert login_page.is_loaded(), "Expected to stay on the login page"


@then(parsers.re(r'I should see the error message "(?P<expected_message>[^"]*)"'))
def assert_error_message(login_page, expected_message):
    actual = login_page.get_login_error()
    assert expected_message in actual, f"Expected {expected_message!r} in {actual!r}"


@then("the search should return no product cards")
def assert_no_results(products_page):
    products_page.assert_no_results()


@then(parsers.re(r'the product "(?P<name>[^"]*)" should be listed at price "(?P<price>[^"]*)"'))
def assert_product_listed_at_price(products_page, product_detail_page, name, price):
    assert products_page.has_product(name), f"Expected {name!r} in the results"
    products_page.open_product(name)
    actual_price = product_detail_page.product_price()
    assert price in actual_price, f"Expected price {price!r}, got {actual_price!r}"
