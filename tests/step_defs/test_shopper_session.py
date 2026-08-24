"""Step definitions for features/shopper_session.feature.

Binds every step in the shopper-session feature to page-object methods only.
No selectors, no raw page calls — the POM boundary is respected throughout.

Conventions (copied from tests/step_defs/test_login.py):
  - Every step the feature uses is declared here; steps are module-scoped.
  - Real logins go through a ROLE resolved by the `credentials` fixture.
  - Invalid/empty data stays literal — it is test data, not a secret.
  - parsers.re with [^"]* is used wherever a quoted value can be empty.
  - Presence is asserted with waiting readers; absence with non-waiting probes.
"""
from pytest_bdd import given, when, then, parsers, scenarios

from config.paths import feature_path

scenarios(str(feature_path("shopper_session")))


# ─────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────

@given("I am on the signup and login page")
def open_login_page(login_page, base_url):
    login_page.open_login_page(base_url)


# ─────────────────────────────────────────────────────────────
# When — authentication
# ─────────────────────────────────────────────────────────────

@when(parsers.re(r'I log in as a "(?P<role>[^"]*)" user$'))
def login_as_role(login_page, credentials, role):
    """Log in with real credentials resolved from the environment."""
    email, password = credentials(role)
    login_page.login_as(email, password)


@when(parsers.re(r'I log in with email "(?P<email>[^"]*)" and password "(?P<password>[^"]*)"'))
def login_with_literal_credentials(login_page, email, password):
    """Literal values, for invalid / malformed / empty-field scenarios."""
    login_page.login_as(email, password)


@when("I clear the credential fields")
def clear_credentials(login_page):
    login_page.clear_credentials()


@when("I log out")
def log_out(nav_page):
    nav_page.logout()


# ─────────────────────────────────────────────────────────────
# When — product browsing and search
# ─────────────────────────────────────────────────────────────

@when("I go to the products page")
def go_to_products(products_page):
    products_page.go_to_products()


@when(parsers.re(r'I search for "(?P<term>[^"]*)"'))
def search_for(products_page, term):
    products_page.search_for(term)


@when(parsers.parse('I open the product "{product_name}" from the search results'))
def open_product_from_results(products_page, product_name):
    products_page.open_product(product_name)


# ─────────────────────────────────────────────────────────────
# When — cart interactions
# ─────────────────────────────────────────────────────────────

@when("I add the product to the cart from the detail page")
def add_to_cart(product_detail_page):
    product_detail_page.add_to_cart()


@when("I view the cart from the added-to-cart modal")
def view_cart_from_modal(product_detail_page):
    product_detail_page.view_cart_from_modal()


@when(parsers.parse('I remove "{product_name}" from the cart'))
def remove_from_cart(cart_page, product_name):
    cart_page.remove_product(product_name)


# ─────────────────────────────────────────────────────────────
# Then — authentication state
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


@then("I should remain on the login page")
def assert_still_on_login(login_page):
    assert login_page.is_loaded(), "Expected to stay on the login page"


@then(parsers.re(r'I should see the error message "(?P<expected_message>[^"]*)"'))
def assert_error_message(login_page, expected_message):
    actual = login_page.get_login_error()
    assert expected_message in actual, f"Expected {expected_message!r} in {actual!r}"


# ─────────────────────────────────────────────────────────────
# Then — search results
# ─────────────────────────────────────────────────────────────

@then(parsers.parse('the search results should show a product named "{product_name}"'))
def assert_search_shows_product(products_page, product_name):
    assert products_page.has_product(product_name), (
        f"Expected {product_name!r} among the search results"
    )


@then(parsers.parse("the search results should contain {count:d} product cards"))
def assert_result_card_count(products_page, count):
    actual = products_page.get_result_count()
    assert actual == count, f"Expected {count} product cards, found {actual}"


# ─────────────────────────────────────────────────────────────
# Then — product detail
# ─────────────────────────────────────────────────────────────

@then(parsers.parse('I should see the product detail for "{product_name}"'))
def assert_product_detail(product_detail_page, product_name):
    assert product_detail_page.is_showing_product(product_name), (
        f"Expected the product detail page for {product_name!r}"
    )


# ─────────────────────────────────────────────────────────────
# Then — cart contents (relative to what this test added/removed)
# ─────────────────────────────────────────────────────────────

@then(parsers.parse('the cart should contain "{product_name}" with quantity {quantity:d}'))
def assert_cart_contains(cart_page, product_name, quantity):
    assert cart_page.has_product(product_name), (
        f"Expected {product_name!r} in the cart"
    )
    actual_qty = cart_page.get_quantity_for(product_name)
    assert actual_qty == str(quantity), (
        f"Expected quantity {quantity} for {product_name!r}, got {actual_qty!r}"
    )


@then(parsers.parse('the cart should no longer contain "{product_name}"'))
def assert_cart_absent(cart_page, product_name):
    cart_page.wait_until_product_absent(product_name)
    assert not cart_page.has_product(product_name), (
        f"Expected {product_name!r} to be gone from the cart"
    )
