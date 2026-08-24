"""Step definitions for features/shopping_session.feature.

Binds the shopping-session scenarios to the login, nav, products,
product-detail and cart page objects. Every step interacts with the UI only
through page-object METHODS — no selectors, no raw page calls.

Conventions copied from the reference login suite:
  - declare every step this feature uses in THIS file (steps are module-scoped)
  - log in by ROLE via the `credentials` fixture; invalid/empty data stays literal
  - use parsers.re with [^"]* wherever a quoted value could be empty
  - assert PRESENCE with waiting readers, ABSENCE with non-waiting probes
  - cart membership is asserted RELATIVE to the product this test added/removed,
    because the shared `registered` account's cart is not guaranteed empty
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
# When — authentication
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


@when("I log out")
def logout(nav_page):
    nav_page.logout()


# ─────────────────────────────────────────────────────────────
# When — products
# ─────────────────────────────────────────────────────────────

@when("I go to the products page")
def go_to_products(products_page):
    products_page.open_listing()


@when(parsers.re(r'I search for "(?P<term>[^"]*)"'))
def search_for(products_page, term):
    products_page.search_for(term)


@when(parsers.re(r'I open the product "(?P<product_name>[^"]*)"'))
def open_product(products_page, product_name):
    products_page.open_product(product_name)


# ─────────────────────────────────────────────────────────────
# When — cart
# ─────────────────────────────────────────────────────────────

@when("I add the product to the cart")
def add_to_cart(product_detail_page):
    product_detail_page.add_to_cart()


@when("I view the cart from the modal")
def view_cart_from_modal(product_detail_page):
    product_detail_page.view_cart_from_modal()


@when(parsers.re(r'I remove "(?P<product_name>[^"]*)" from the cart'))
def remove_from_cart(cart_page, product_name):
    cart_page.remove_product(product_name)


# ─────────────────────────────────────────────────────────────
# Then — authentication
# ─────────────────────────────────────────────────────────────

@then("I should be logged in")
def assert_logged_in(nav_page):
    """The Logout link renders only while authenticated — a more reliable
    signal than the URL, which this app serves the same either way."""
    assert nav_page.wait_until_logged_in(), "No session after logging in"


@then("I should not be logged in")
def assert_not_logged_in(nav_page):
    """Non-waiting probe. The waiting reader would time out rather than return
    False, so the assertion would never be reached."""
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
# Then — products
# ─────────────────────────────────────────────────────────────

@then("the products listing should be shown")
def assert_products_listing(products_page):
    assert products_page.is_loaded(), "Expected the products listing to load"


@then(parsers.re(r'the search results should include "(?P<product_name>[^"]*)"'))
def assert_search_includes(products_page, product_name):
    assert products_page.search_has_executed(), "Expected the search to execute"
    assert products_page.has_result_for(product_name), \
        f"Expected {product_name!r} among the search results"


@then("the search results should contain no product cards")
def assert_no_result_cards(products_page):
    assert products_page.search_has_executed(), "Expected the search to execute"
    assert products_page.get_result_card_count() == 0, \
        "Expected zero product cards for a term matching nothing"


# ─────────────────────────────────────────────────────────────
# Then — product detail
# ─────────────────────────────────────────────────────────────

@then(parsers.re(r'the product detail page should show the product name "(?P<product_name>[^"]*)"'))
def assert_detail_product_name(product_detail_page, product_name):
    assert product_detail_page.is_loaded(), "Expected the product detail page to load"
    actual = product_detail_page.get_product_name()
    assert product_name in actual, f"Expected {product_name!r} in {actual!r}"


# ─────────────────────────────────────────────────────────────
# Then — cart
# ─────────────────────────────────────────────────────────────

@then(parsers.re(r'the cart should contain "(?P<product_name>[^"]*)" with quantity (?P<quantity>\d+)'))
def assert_cart_contains(cart_page, product_name, quantity):
    assert cart_page.is_loaded(), "Expected the cart page to load"
    assert cart_page.contains_product(product_name), \
        f"Expected {product_name!r} in the cart"
    actual_qty = cart_page.get_quantity_for(product_name)
    assert actual_qty == quantity, \
        f"Expected quantity {quantity!r} for {product_name!r}, got {actual_qty!r}"


@then(parsers.re(r'the cart should no longer contain "(?P<product_name>[^"]*)"'))
def assert_cart_absent(cart_page, product_name):
    """Relative absence: this product the test just removed is gone. Waits for
    the row to disappear rather than reading a snapshot straight after the
    removal, when the cart is still settling."""
    cart_page.wait_until_absent(product_name)
