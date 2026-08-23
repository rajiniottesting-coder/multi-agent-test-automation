"""Step definitions for features/shopping_session.feature.

Binds the shopping-session scenarios to page-object methods. Follows the login
reference style: page-object calls only, no selectors here; parsers.re with
[^"]* wherever a quoted value can be empty; presence asserted with waiting
readers and absence with non-waiting probes.
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


@given("the cart is empty")
def empty_the_cart(cart_page, base_url):
    """Own the starting state: clear the persistent cart so absolute
    emptiness assertions later in the scenario are honest."""
    cart_page.open_cart(base_url)
    cart_page.empty_the_cart()


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
    login_page.login_as(email, "WrongPass123!")


@when(parsers.re(r'I log in with email "(?P<email>[^"]*)" and password "(?P<password>[^"]*)"'))
def login_with_literal_credentials(login_page, email, password):
    login_page.login_as(email, password)


@when("I clear the credential fields")
def clear_credentials(login_page):
    login_page.clear_credentials()


@when("I log out")
def log_out(nav_page):
    nav_page.logout()


@when(parsers.re(r'I search for "(?P<term>[^"]*)" on the products page'))
def search_for_term(products_page, term):
    products_page.search_for(term)


@when(parsers.parse('I open the product "{product_name}" from the search results'))
def open_product_from_results(products_page, product_name):
    products_page.open_product(product_name)


@when("I add the product to the cart from the detail page")
def add_product_to_cart(product_detail_page):
    product_detail_page.add_product_to_cart()


@when("I choose to view the cart from the modal")
def view_cart_from_modal(product_detail_page):
    product_detail_page.view_cart_from_modal()


@when("I dismiss the modal with Continue Shopping")
def dismiss_modal(product_detail_page):
    product_detail_page.continue_shopping()


@when("I open the cart from the navigation")
def open_cart_from_nav(nav_page):
    nav_page.go_to_cart()


@when(parsers.parse('I remove the product "{product_name}" from the cart'))
def remove_product(cart_page, product_name):
    cart_page.remove_product(product_name)


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


@then("I should not see my account name in the navigation")
def assert_account_name_hidden(nav_page):
    assert not nav_page.is_logged_in(), "Still showing a logged-in session"


@then(parsers.re(r'I should see the error message "(?P<expected_message>[^"]*)"'))
def assert_error_message(login_page, expected_message):
    actual = login_page.get_login_error()
    assert expected_message in actual, f"Expected {expected_message!r} in {actual!r}"


@then(parsers.parse('I should see the product "{product_name}" in the search results'))
def assert_product_in_results(products_page, product_name):
    assert products_page.has_searched(), "Search does not appear to have executed"
    assert products_page.has_product(product_name), (
        f"Expected {product_name!r} in the search results"
    )


@then(parsers.parse('I should see the product detail page for "{product_name}"'))
def assert_product_detail(product_detail_page, product_name):
    assert product_detail_page.is_loaded(timeout_ms=10000), (
        "Product detail page did not load"
    )
    name = product_detail_page.product_name()
    assert product_name in name, f"Expected {product_name!r} on detail page, got {name!r}"


@then("I should be on the cart page")
def assert_on_cart_page(cart_page):
    assert cart_page.is_loaded(), "Expected to be on the cart page"


@then(parsers.parse('the cart should contain the product "{product_name}"'))
def assert_cart_contains(cart_page, product_name):
    assert cart_page.has_product(product_name), (
        f"Expected {product_name!r} in the cart"
    )


@then(parsers.parse('the cart should not contain the product "{product_name}"'))
def assert_cart_not_contains(cart_page, product_name):
    assert not cart_page.has_product(product_name), (
        f"Did not expect {product_name!r} in the cart"
    )


@then("the cart should be empty")
def assert_cart_empty(cart_page):
    assert cart_page.is_empty(), "Expected the cart to be empty"


@then("no product cards should be shown")
def assert_no_product_cards(products_page):
    count = products_page.get_result_count()
    assert count == 0, f"Expected zero product cards, found {count}"


@then("the search should not error out")
def assert_search_no_error(products_page):
    assert products_page.is_loaded(), "The products page errored out after searching"
