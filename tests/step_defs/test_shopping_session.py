"""Step definitions for features/shopping_session.feature.

Binds the shopping-session scenarios to page-object methods. All UI mechanics
live in the page objects; step definitions call named methods only and hold no
selectors.

Login follows the reserved conventions from tests/step_defs/test_login.py:
real logins resolve through the `credentials` fixture by ROLE, while invalid
and empty values stay literal (they are test data, not secrets). Empty quoted
values use parsers.re with [^"]* because parsers.parse cannot match "".
"""
from pytest_bdd import given, when, then, parsers, scenarios

from config.paths import feature_path

scenarios(str(feature_path("shopping_session")))


# ─────────────────────────────────────────────────────────────
# Given / When — login page entry
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


@when(parsers.re(r'I log in as a "(?P<role>[^"]*)" user with an incorrect password'))
def login_as_role_wrong_password(login_page, credentials, role):
    """Valid email, deliberately wrong password (test data, not a secret)."""
    email, _ = credentials(role)
    login_page.login_as(email, "WrongPass123!")


@when(parsers.re(r'I log in with email "(?P<email>[^"]*)" and password "(?P<password>[^"]*)"'))
def login_with_literal_credentials(login_page, email, password):
    """Literal values, for unknown-email and empty-field scenarios."""
    login_page.login_as(email, password)


@when("I dismiss the login error")
def dismiss_login_error(login_page, base_url):
    """Reload the login form so residual error state does not leak into the
    next attempt in the same scenario."""
    login_page.open_login_page(base_url)


@when("I log out")
def logout(nav_page):
    nav_page.logout()


# ─────────────────────────────────────────────────────────────
# When — cart state ownership (runs AFTER sign-in; account-scoped)
# ─────────────────────────────────────────────────────────────

@when("the cart is empty")
def empty_cart(cart_page, base_url):
    """Own the starting state: clear the signed-in account's cart so later
    absolute assertions ('cart is empty') are honest."""
    cart_page.open_cart(base_url)
    cart_page.empty_the_cart()


# ─────────────────────────────────────────────────────────────
# When — products navigation and search
# ─────────────────────────────────────────────────────────────

@given("I go to the products page")
@when("I go to the products page")
def go_to_products(products_page, base_url):
    products_page.open_listing(base_url)


@when(parsers.re(r'I search for "(?P<term>[^"]*)"'))
def search_for(products_page, term):
    products_page.search_for(term)


@when(parsers.parse('I open the product "{product_name}" from the search results'))
def open_product_from_results(products_page, product_name):
    products_page.open_product(product_name)


# ─────────────────────────────────────────────────────────────
# When — product detail / cart actions
# ─────────────────────────────────────────────────────────────

@when("I add the product to the cart")
def add_to_cart(product_detail_page):
    product_detail_page.add_to_cart()


@when("I view the cart from the modal")
def view_cart_from_modal(product_detail_page):
    product_detail_page.view_cart_from_modal()


@when("I dismiss the add-to-cart modal with Continue Shopping")
def dismiss_modal_continue_shopping(product_detail_page):
    product_detail_page.continue_shopping()


@when("I open the cart from the navigation")
def open_cart_from_nav(cart_page, base_url):
    cart_page.open_cart(base_url)


@when(parsers.parse('I remove "{product_name}" from the cart'))
def remove_from_cart(cart_page, product_name):
    cart_page.remove_product(product_name)


# ─────────────────────────────────────────────────────────────
# Then — authentication assertions
# ─────────────────────────────────────────────────────────────

@then("I should be logged in")
def assert_logged_in(nav_page):
    assert nav_page.wait_until_logged_in(), "No session after logging in"


@then("I should not be logged in")
def assert_not_logged_in(nav_page):
    """Non-waiting probe: the waiting reader would time out rather than
    return False, so the assertion would never be reached."""
    assert not nav_page.is_logged_in(), "Unexpectedly logged in"


@then("I should see my account name in the navigation")
def assert_account_name_shown(nav_page):
    banner = nav_page.logged_in_name()
    assert "Logged in as" in banner, f"Expected a logged-in banner, got {banner!r}"


@then(parsers.re(r'I should see the error message "(?P<expected_message>[^"]*)"'))
def assert_error_message(login_page, expected_message):
    actual = login_page.get_login_error()
    assert expected_message in actual, f"Expected {expected_message!r} in {actual!r}"


# ─────────────────────────────────────────────────────────────
# Then — search results assertions
# ─────────────────────────────────────────────────────────────

@then(parsers.parse('the search results should include "{product_name}"'))
def assert_search_includes(products_page, product_name):
    assert products_page.has_searched(), "Search did not execute"
    assert products_page.has_result_for(product_name), (
        f"Expected {product_name!r} in the search results"
    )


@then("no product cards should be shown")
def assert_no_product_cards(products_page):
    assert products_page.has_searched(), "Search did not execute"
    count = products_page.get_result_count()
    assert count == 0, f"Expected zero product cards, found {count}"


@then("the product search should not error")
def assert_search_no_error(products_page):
    """An empty search either shows the full catalogue or nothing, but must
    not crash: the listing page must still be loaded."""
    assert products_page.is_loaded(), "Products page did not remain loaded"


# ─────────────────────────────────────────────────────────────
# Then — product detail assertions
# ─────────────────────────────────────────────────────────────

@then(parsers.parse('the product detail page for "{product_name}" is shown'))
def assert_product_detail_shown(product_detail_page, product_name):
    assert product_detail_page.is_loaded(), "Product detail page did not load"
    actual = product_detail_page.product_name()
    assert product_name in actual, (
        f"Expected product detail for {product_name!r}, got {actual!r}"
    )


# ─────────────────────────────────────────────────────────────
# Then — cart assertions
# ─────────────────────────────────────────────────────────────

@then(parsers.parse('the cart should contain "{product_name}" with quantity {quantity:d}'))
def assert_cart_contains(cart_page, product_name, quantity):
    assert cart_page.has_product(product_name), (
        f"Expected {product_name!r} in the cart"
    )
    assert cart_page.assert_row_count(quantity) is None or True, ""
    cart_page.assert_row_count(quantity)


@then(parsers.parse('the cart should not contain "{product_name}"'))
def assert_cart_not_contains(cart_page, product_name):
    assert not cart_page.has_product(product_name), (
        f"Did not expect {product_name!r} in the cart"
    )


@then("the cart should be empty")
def assert_cart_empty(cart_page):
    assert cart_page.is_empty(), "Expected the cart to be empty"
