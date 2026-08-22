"""Step definitions for features/shopping_session.feature.

Binds the shopping-session scenarios to page objects only. No selectors, no
raw Playwright calls, no scenario data hardcoded into step bodies.

Presence is asserted with waiting readers; absence with non-waiting probes.
Real logins go through the `credentials` fixture by ROLE; invalid and empty
credentials stay literal because they are test data, not secrets.
"""
from pytest_bdd import given, when, then, parsers, scenarios

from config.paths import feature_path

scenarios(str(feature_path("shopping_session")))


# ─────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────

@given("a newly registered account")
def newly_registered_account(login_page, base_url, unique_username):
    """Start signup for a fresh account so this session owns its cart state.

    The unique_username fixture guarantees the identifier is run-unique on the
    shared application, so an absolute empty-cart assertion is meaningful.
    """
    login_page.open_login_page(base_url)
    login_page.start_signup(unique_username, f"{unique_username}@example.com")


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
    login_page.login_as(email, "definitely-not-the-password")


@when(parsers.re(r'I log in with email "(?P<email>[^"]*)" and password "(?P<password>[^"]*)"'))
def login_with_literal_credentials(login_page, email, password):
    login_page.login_as(email, password)


@when("I clear the credential fields")
def clear_credentials(login_page):
    login_page.clear_credentials()


@when("I open the products page")
def open_products(nav_page):
    nav_page.open_products()


@when(parsers.parse('I search for "{term}"'))
def search_for(products_page, term):
    products_page.search_for(term)


@when(parsers.parse('I open the product detail for "{product_name}"'))
def open_product_detail(products_page, product_name):
    products_page.open_product_detail(product_name)


@when("I add the product to the cart")
def add_to_cart(product_detail_page):
    product_detail_page.add_to_cart()


@when("I view the cart from the product modal")
def view_cart_from_modal(product_detail_page):
    product_detail_page.view_cart_from_modal()


@when(parsers.parse('I remove the product "{product_name}" from the cart'))
def remove_product(cart_page, product_name):
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


@then("I should see my account name in the navigation")
def assert_account_name_shown(nav_page):
    banner = nav_page.logged_in_name()
    assert "Logged in as" in banner, f"Expected a logged-in banner, got {banner!r}"


@then("the search results should be shown")
def assert_search_results_shown(products_page):
    assert products_page.search_executed(), "Search did not execute"


@then(parsers.parse('I should see the product "{product_name}" in the results'))
def assert_product_in_results(products_page, product_name):
    assert products_page.has_product(product_name), (
        f"Expected {product_name!r} in the search results"
    )


@then(parsers.parse('I should see the product name "{product_name}" on the detail page'))
def assert_detail_product_name(product_detail_page, product_name):
    actual = product_detail_page.get_product_name()
    assert product_name in actual, f"Expected {product_name!r} in {actual!r}"


@then(parsers.parse('the cart should contain {count:d} item'))
def assert_cart_item_count(cart_page, count):
    cart_page.assert_row_count(count)


@then(parsers.parse('the cart should contain the product "{product_name}"'))
def assert_cart_has_product(cart_page, product_name):
    assert cart_page.has_product(product_name), (
        f"Expected {product_name!r} in the cart"
    )


@then("the cart should be empty")
def assert_cart_empty(cart_page):
    assert cart_page.is_empty(), "Expected the cart to be empty"


@then("I should not be logged in")
def assert_not_logged_in(nav_page):
    assert not nav_page.is_logged_in(), "Unexpectedly logged in"


@then("I should see the login and signup link")
def assert_signup_login_visible(nav_page):
    assert nav_page.wait_until_logged_out(), "Expected the Login/Signup link"


@then(parsers.re(r'I should see the error message "(?P<expected_message>[^"]*)"'))
def assert_error_message(login_page, expected_message):
    actual = login_page.get_login_error()
    assert expected_message in actual, f"Expected {expected_message!r} in {actual!r}"


@then("I should remain on the login page")
def assert_still_on_login(login_page):
    assert login_page.is_loaded(), "Expected to stay on the login page"


@then("no products should be displayed in the results")
def assert_no_products(products_page):
    products_page.assert_result_count(0)
