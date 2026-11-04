"""Step definitions for features/shopping_session.feature.

Covers a full shopping session (login → search → add → cart → remove → logout),
a rejected login with literal bad credentials, and an empty search result.

All UI interaction goes through page-object methods. Steps reused from the
committed login suite are re-declared here (pytest-bdd steps are module-scoped)
and assert exactly what the committed definitions assert.
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
    """Literal values, for the invalid-credentials scenario."""
    login_page.login_as(email, password)


@when("I go to the products page")
def go_to_products(nav_page):
    nav_page.go_to_products()


@when(parsers.parse('I search for "{term}"'))
def search_for(products_page, term):
    products_page.search_for(term)


@when(parsers.parse('I open the product "{product_name}" from the search results'))
def open_product_from_results(products_page, product_name):
    products_page.open_product_details(product_name)


@when("I add the displayed product to the cart")
def add_displayed_product(product_detail_page):
    product_detail_page.add_to_cart()


@when("I view the cart from the add-to-cart modal")
def view_cart_from_modal(product_detail_page):
    product_detail_page.view_cart()


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
    """The Logout link is rendered only while authenticated, which is more
    reliable than the URL: this app serves the same path either way."""
    assert nav_page.wait_until_logged_in(), "No session after logging in"


@then("I should see my account name in the navigation")
def assert_account_name_shown(nav_page):
    banner = nav_page.logged_in_name()
    assert "Logged in as" in banner, f"Expected a logged-in banner, got {banner!r}"


@then(parsers.parse('the search results should include the product "{product_name}"'))
def assert_search_includes(products_page, product_name):
    products_page.wait_for_product_in_results(product_name)
    assert products_page.has_product(product_name), (
        f"Expected search results to include {product_name!r}"
    )


@then(parsers.parse('I should see the product name "{expected_name}" on the detail page'))
def assert_detail_name(product_detail_page, expected_name):
    actual = product_detail_page.product_name()
    assert expected_name in actual, f"Expected {expected_name!r} in {actual!r}"


@then(parsers.parse('I should see the product price "{expected_price}" on the detail page'))
def assert_detail_price(product_detail_page, expected_price):
    actual = product_detail_page.product_price()
    assert expected_price in actual, f"Expected {expected_price!r} in {actual!r}"


@then(parsers.parse('the cart should list the product "{product_name}"'))
def assert_cart_lists(cart_page, product_name):
    cart_page.wait_for_product(product_name, present=True)
    assert cart_page.has_product(product_name), (
        f"Expected the cart to list {product_name!r}"
    )


@then(parsers.parse('the cart should not list the product "{product_name}"'))
def assert_cart_absent(cart_page, product_name):
    cart_page.wait_for_product(product_name, present=False)
    assert cart_page.is_product_absent(product_name), (
        f"Expected {product_name!r} to be absent from the cart"
    )


@then("I should not be logged in")
def assert_not_logged_in(nav_page):
    """Non-waiting probe. The waiting reader would time out rather than
    return False, so the assertion would never be reached."""
    assert not nav_page.is_logged_in(), "Unexpectedly logged in"


@then("I should see the signup and login link in the navigation")
def assert_signup_login_shown(nav_page):
    assert nav_page.wait_until_logged_out(), "Signup / Login link not shown"


@then(parsers.re(r'I should see the error message "(?P<expected_message>[^"]*)"'))
def assert_error_message(login_page, expected_message):
    actual = login_page.get_login_error()
    assert expected_message in actual, f"Expected {expected_message!r} in {actual!r}"


@then("I should remain on the login page")
def assert_still_on_login(login_page):
    assert login_page.is_loaded(), "Expected to stay on the login page"


@then("no product result cards should be shown")
def assert_no_product_cards(products_page):
    assert products_page.has_no_product_cards(), (
        "Expected no product result cards to be shown"
    )
