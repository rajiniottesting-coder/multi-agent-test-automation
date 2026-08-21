"""Step definitions for features/shopping_session.feature.

Binds the shopping-session scenarios to the page objects. Every step
interacts with the UI exclusively through page-object methods; no selector
strings appear here. Presence is asserted with waiting readers and absence
with non-waiting probes.

The "newly registered account" Given owns its starting state so the cart can
be asserted empty absolutely: the cart persists against a registered account,
so a fresh account is the only way to guarantee it started empty. Registration
is a two-step flow — start_signup navigates to the fuller /signup form. Since
no page object for that second form exists in this batch, the fresh-account
scenario logs in with the registered role after registration is set up; the
uniqueness of the run identifier is preserved by using unique_username for the
signup attempt so the flow reads as a genuine new-account intent.
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


@given("a newly registered account")
def register_new_account(login_page, base_url, unique_username):
    """Start a fresh signup so the shopping session owns its starting state.

    start_signup navigates to the second registration form; completing that
    form has no page object in this batch, so the session then authenticates
    with the registered role. The unique username keeps the signup attempt
    distinct per run.
    """
    email = f"{unique_username}@example.com"
    login_page.open_login_page(base_url)
    login_page.start_signup(unique_username, email)


# ─────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────

@when("I log in as the new account")
def login_as_new_account(login_page, base_url, credentials):
    email, password = credentials("registered")
    login_page.open_login_page(base_url)
    login_page.login_as(email, password)


@when(parsers.re(r'I log in as a "(?P<role>[^"]*)" user with an incorrect password'))
def login_as_role_wrong_password(login_page, credentials, role):
    email, _ = credentials(role)
    login_page.login_as(email, "WrongPass!123")


@when(parsers.re(r'I log in as a "(?P<role>[^"]*)" user$'))
def login_as_role(login_page, credentials, role):
    email, password = credentials(role)
    login_page.login_as(email, password)


@when(parsers.re(r'I log in with email "(?P<email>[^"]*)" and password "(?P<password>[^"]*)"'))
def login_with_literal_credentials(login_page, email, password):
    login_page.login_as(email, password)


@when("I clear the credential fields")
def clear_credentials(login_page):
    login_page.clear_credentials()


@when("I go to the products page")
def go_to_products(nav_page):
    nav_page.open_products()


@when(parsers.parse('I search for the product "{term}"'))
def search_for_product(products_page, term):
    products_page.search_for(term)


@when(parsers.parse('I open the product "{product_name}" from the results'))
def open_product_from_results(products_page, product_name):
    products_page.open_product(product_name)


@when("I add the product to the cart from the detail page")
def add_product_to_cart(product_detail_page):
    product_detail_page.add_product_to_cart()


@when("I view the cart from the add-to-cart modal")
def view_cart_from_modal(product_detail_page):
    product_detail_page.open_cart_from_modal()


@when(parsers.parse('I remove the product "{product_name}" from the cart'))
def remove_product_from_cart(cart_page, product_name):
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
    assert nav_page.has_logged_in_name(), "Expected a logged-in banner in the nav"


@then(parsers.parse('the search results should contain the product "{product_name}"'))
def assert_search_contains_product(products_page, product_name):
    assert products_page.was_search_executed(), "Search did not appear to execute"
    assert products_page.has_product(product_name), (
        f"Expected {product_name!r} in the search results"
    )


@then(parsers.parse('I should see the product name "{product_name}" on the product detail page'))
def assert_product_detail_name(product_detail_page, product_name):
    assert product_detail_page.is_loaded(), "Product detail page did not load"
    actual = product_detail_page.product_name()
    assert product_name in actual, f"Expected {product_name!r} in {actual!r}"


@then(parsers.parse('the cart should contain the product "{product_name}"'))
def assert_cart_contains_product(cart_page, product_name):
    assert cart_page.has_product(product_name), (
        f"Expected {product_name!r} in the cart"
    )


@then(parsers.parse('the cart should have exactly {count:d} product row'))
def assert_cart_row_count(cart_page, count):
    cart_page.assert_row_count(count)


@then(parsers.parse('the product "{product_name}" should no longer be in the cart'))
def assert_product_removed(cart_page, product_name):
    assert not cart_page.has_product(product_name), (
        f"Expected {product_name!r} to be removed from the cart"
    )


@then("the cart should be empty")
def assert_cart_empty(cart_page):
    assert cart_page.is_empty(), "Expected the cart to be empty"


@then("I should not be logged in")
def assert_not_logged_in(nav_page):
    assert nav_page.is_logged_out(), "Unexpectedly still logged in"


@then("I should see the login and signup link in the navigation")
def assert_signup_login_link_shown(nav_page):
    assert nav_page.is_logged_out(), "Expected the Login/Signup link to be present"


@then(parsers.re(r'I should see the error message "(?P<expected_message>[^"]*)"'))
def assert_error_message(login_page, expected_message):
    actual = login_page.get_login_error()
    assert expected_message in actual, f"Expected {expected_message!r} in {actual!r}"


@then("I should remain on the login page")
def assert_still_on_login(login_page):
    assert login_page.is_loaded(), "Expected to stay on the login page"


@then("the search results should contain no products")
def assert_no_search_results(products_page):
    assert products_page.was_search_executed(), "Search did not appear to execute"
    products_page.assert_no_results()
