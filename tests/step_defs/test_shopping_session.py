"""Step definitions for features/shopping_session.feature.

Binds the end-to-end shopping-session scenarios to page-object methods.
Every step phrase used by the feature is declared here — pytest-bdd steps are
module-scoped, so steps in other modules are not visible.

Rules honoured:
- Call page-object methods only; no selectors in this file.
- parsers.re with [^"]* where a quoted value may be empty ("").
- Presence asserted with waiting readers; absence with non-waiting probes.
- Login by ROLE via the `credentials` fixture; invalid/literal data stays literal.
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


@given("I open the products page")
@when("I open the products page")
def open_products_page(products_page, base_url):
    products_page.open_listing(base_url)


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


@when("I empty the cart")
def empty_the_cart(cart_page, base_url):
    cart_page.open_cart(base_url)
    cart_page.empty_the_cart()


@when(parsers.re(r'I search for "(?P<term>[^"]*)"'))
def search_for(products_page, term):
    products_page.search_for(term)


@when(parsers.parse('I open the product "{product_name}" from the search results'))
def open_product_from_results(products_page, product_name):
    products_page.open_product(product_name)


@when("I add the product to the cart from the detail page")
def add_to_cart_from_detail(product_detail_page):
    product_detail_page.add_to_cart()


@when("I follow the View Cart link in the modal")
def follow_view_cart_link(product_detail_page):
    product_detail_page.view_cart_from_modal()


@when("I dismiss the modal with Continue Shopping")
def dismiss_modal_continue_shopping(product_detail_page):
    product_detail_page.continue_shopping()


@when("I open the cart from the navigation")
def open_cart_from_nav(cart_page, base_url):
    cart_page.open_cart(base_url)


@when(parsers.parse('I remove "{product_name}" from the cart'))
def remove_from_cart(cart_page, product_name):
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
    assert not nav_page.is_logged_in(), "Unexpectedly logged in"


@then("I should see my account name in the navigation")
def assert_account_name_shown(nav_page):
    banner = nav_page.logged_in_name()
    assert "Logged in as" in banner, f"Expected a logged-in banner, got {banner!r}"


@then(parsers.parse('I should see a product card for "{product_name}"'))
def assert_product_card_shown(products_page, product_name):
    assert products_page.has_search_executed(), "Search never executed"
    assert products_page.has_product_card(product_name), (
        f"Expected a product card for {product_name!r}"
    )


@then(parsers.parse('I should see the product detail page for "{product_name}"'))
def assert_product_detail_shown(product_detail_page, product_name):
    assert product_detail_page.is_showing_product(product_name), (
        f"Expected the product detail page for {product_name!r}"
    )


@then(parsers.parse('I should remain on the product detail page for "{product_name}"'))
def assert_still_on_product_detail(product_detail_page, product_name):
    assert product_detail_page.is_showing_product(product_name), (
        f"Expected to remain on the product detail page for {product_name!r}"
    )


@then(parsers.parse('the cart should contain "{product_name}" with quantity {quantity:d}'))
def assert_cart_contains(cart_page, product_name, quantity):
    assert cart_page.has_product(product_name), (
        f"Expected {product_name!r} in the cart"
    )
    actual = cart_page.get_quantity_for(product_name)
    assert actual == quantity, (
        f"Expected quantity {quantity} for {product_name!r}, got {actual}"
    )


@then("the cart should be empty")
def assert_cart_empty(cart_page):
    assert cart_page.is_empty(), "Expected the cart to be empty"


@then("no product cards should be shown")
def assert_no_product_cards(products_page):
    assert products_page.get_result_count() == 0, (
        "Expected no product cards for a non-matching search"
    )


@then(parsers.parse('the search should not falsely match "{term}"'))
def assert_no_false_match(products_page, term):
    names = products_page.get_product_names()
    assert not any(term in name for name in names), (
        f"Search falsely matched {term!r} in {names!r}"
    )


@then(parsers.re(r'I should see the error message "(?P<expected_message>[^"]*)"'))
def assert_error_message(login_page, expected_message):
    actual = login_page.get_login_error()
    assert expected_message in actual, f"Expected {expected_message!r} in {actual!r}"
