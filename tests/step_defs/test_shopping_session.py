"""Step definitions for features/shopping_session.feature.

Binds the shopping-session scenarios to page-object methods only. No selectors
appear here — every UI interaction goes through a page object. Real logins go
through a ROLE resolved by the `credentials` fixture; invalid, malformed and
empty values stay literal because they are test data, not secrets.

Cart assertions are RELATIVE (the row this scenario added is present / gone),
never absolute. The `cart` inventory page is declared persistent_state: the
application keeps the cart against the signed-in account, it survives logout
and survives the run, and this application declares no way to establish a clean
start. An absolute count would count a previous run's leftovers too, and no
wait removes them. The relative assertion holds whatever the state started as.
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


@when(parsers.re(r'I log in with email "(?P<email>[^"]*)" and password "(?P<password>[^"]*)"'))
def login_with_literal_credentials(login_page, email, password):
    """Literal values, for invalid, malformed and empty-field scenarios."""
    login_page.login_as(email, password)


@when("I clear the credential fields")
def clear_credentials(login_page):
    login_page.clear_credentials()


@when("I dismiss the login error")
def dismiss_login_error(login_page, base_url):
    """Reload the login form so the previous attempt's error banner cannot be
    read as the next attempt's response."""
    login_page.open_login_page(base_url)


@when("I go to the products page")
def go_to_products(nav_page):
    nav_page.go_to_products()


@when(parsers.re(r'I search for "(?P<term>[^"]*)"'))
def search_for(products_page, term):
    products_page.search_for(term)


@when(parsers.parse('I view the product "{product_name}"'))
def view_product(products_page, product_name):
    products_page.open_product(product_name)


@when("I add the product to the cart from the product detail page")
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


@then(parsers.parse('I should see a product card for "{product_name}"'))
def assert_search_contains(products_page, product_name):
    assert products_page.has_result(product_name), (
        f"Expected a product card for {product_name!r} among the search results"
    )


@then("I should see no product cards in the search results")
def assert_no_result_cards(products_page):
    assert products_page.has_no_results(), "Expected zero product cards"


@then(parsers.parse('I should see the product name "{product_name}"'))
def assert_product_detail_name(product_detail_page, product_name):
    actual = product_detail_page.product_detail_name()
    assert actual == product_name, f"Expected {product_name!r}, got {actual!r}"


@then(parsers.parse('the cart should contain a row for "{product_name}" with quantity {quantity:d}'))
def assert_cart_row(cart_page, product_name, quantity):
    """RELATIVE assertion: the cart is persistent_state and this app offers no
    clean-start, so we assert only that the row THIS scenario added is present
    with the expected quantity — true whatever the cart started with. The
    quantity reader returns a string; compare against the same type."""
    cart_page.wait_for_product_present(product_name)
    actual = cart_page.get_quantity_for(product_name)
    assert int(actual) == quantity, (
        f"Expected quantity {quantity} for {product_name!r}, got {actual!r}"
    )


@then(parsers.parse('the cart should not contain a row for "{product_name}"'))
def assert_cart_row_absent(cart_page, product_name):
    """RELATIVE absence: wait for THIS scenario's row to be gone, not for the
    whole cart to be empty — other items may pre-exist on the shared account."""
    cart_page.wait_for_product_absent(product_name)


@then("I should remain on the login page")
def assert_still_on_login(login_page):
    assert login_page.is_loaded(), "Expected to stay on the login page"


@then(parsers.re(r'I should see the error message "(?P<expected_message>[^"]*)"'))
def assert_login_error(login_page, expected_message):
    actual = login_page.get_login_error()
    assert expected_message in actual, f"Expected {expected_message!r} in {actual!r}"
