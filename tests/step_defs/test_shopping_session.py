"""Step definitions for features/shopping_session.feature.

Every step the feature uses is declared here — steps are module-scoped, so a
step defined in another module is not visible in this one. Page-object
FIXTURES (login_page, nav_page, products_page, product_detail_page, cart_page)
resolve hierarchically from tests/step_defs/conftest.py.

Rules honoured:
- Interact with the UI only through page-object methods; no selectors here.
- Log in by ROLE via the `credentials` fixture; invalid/empty data stays literal.
- parsers.re with [^"]* wherever a quoted value can be empty.
- Presence uses waiting readers; absence uses non-waiting probes.
"""
from pytest_bdd import given, when, then, parsers, scenarios

from config.paths import feature_path

scenarios(str(feature_path("shopping_session")))


# ─────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────

@given("I am on the signup and login page")
def open_login_page(login_page, base_url):
    login_page.open(base_url)


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


@when("I log out")
def do_logout(nav_page):
    nav_page.logout()


@when("I go to the products page")
def go_to_products(nav_page):
    nav_page.go_to_products()


@when(parsers.re(r'I search for "(?P<term>[^"]*)"'))
def search_products(products_page, term):
    products_page.search_for(term)


@when(parsers.re(r'I open the product "(?P<product_name>[^"]*)" from the results'))
def open_product_from_results(products_page, product_name):
    products_page.open_product(product_name)


@when("I add the product to the cart from the detail page")
def add_product_to_cart(product_detail_page):
    product_detail_page.add_product_to_cart()


@when("I view the cart from the added-to-cart modal")
def view_cart_from_modal(product_detail_page):
    product_detail_page.open_cart_from_modal()


@when(parsers.re(r'I remove the product "(?P<product_name>[^"]*)" from the cart'))
def remove_product_from_cart(cart_page, product_name):
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


@then("the search results should be displayed")
def assert_search_results_shown(products_page):
    assert products_page.is_search_results_shown(), "Search did not execute"


@then(parsers.re(r'I should see the product "(?P<product_name>[^"]*)" in the results'))
def assert_product_in_results(products_page, product_name):
    assert products_page.has_result_named(product_name), (
        f"Expected {product_name!r} in results, got {products_page.get_result_names()!r}"
    )


@then(parsers.re(r'the product detail page should show the product name "(?P<product_name>[^"]*)"'))
def assert_detail_product_name(product_detail_page, product_name):
    actual = product_detail_page.product_name()
    assert product_name in actual, f"Expected {product_name!r} in {actual!r}"


@then(parsers.parse("the cart should contain exactly {count:d} item"))
def assert_cart_item_count(cart_page, count):
    actual = cart_page.get_row_count()
    assert actual == count, f"Expected {count} cart row(s), found {actual}"


@then(parsers.re(r'the cart should contain the product "(?P<product_name>[^"]*)"'))
def assert_cart_has_product(cart_page, product_name):
    assert cart_page.has_product(product_name), (
        f"Expected {product_name!r} in cart, got {cart_page.get_product_names()!r}"
    )


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


@then("no products should be shown in the results")
def assert_no_results(products_page):
    count = products_page.get_result_card_count()
    assert count == 0, f"Expected zero result cards, found {count}"
