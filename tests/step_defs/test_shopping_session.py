"""Step definitions for features/shopping_session.feature.

Binds the shopping-session scenarios to page-object methods. Selectors never
appear here — every UI interaction goes through a page-object method. Logins
resolve real credentials through the `credentials` fixture by ROLE.

Presence is asserted with waiting readers; absence with non-waiting probes.
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
    """Log in with real credentials resolved from the environment."""
    email, password = credentials(role)
    login_page.login_as(email, password)


@when("I go to the products page")
def go_to_products(nav_page):
    nav_page.open_products()


@when(parsers.re(r'I search for the product "(?P<term>[^"]*)"'))
def search_for_product(products_page, term):
    products_page.search_for(term)


@when(parsers.re(r'I open the product "(?P<product_name>[^"]*)" from the results'))
def open_product_from_results(products_page, product_name):
    products_page.open_product(product_name)


@when("I add the product to the cart from the detail page")
def add_product_to_cart(product_detail_page):
    product_detail_page.add_to_cart()


@when("I view the cart from the add-to-cart modal")
def view_cart_from_modal(product_detail_page):
    product_detail_page.view_cart_from_modal()


@when(parsers.re(r'I remove the product "(?P<product_name>[^"]*)" from the cart'))
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
    banner = nav_page.logged_in_name()
    assert "Logged in as" in banner, f"Expected a logged-in banner, got {banner!r}"


@then("I should see search results")
def assert_search_results(products_page):
    assert products_page.has_searched(), "Search does not appear to have executed"
    assert products_page.get_result_card_count() > 0, "Expected one or more results"


@then(parsers.re(r'I should see the product "(?P<product_name>[^"]*)" in the results'))
def assert_product_in_results(products_page, product_name):
    assert products_page.has_product(product_name), (
        f"Expected {product_name!r} in results {products_page.get_result_names()!r}"
    )


@then(parsers.re(r'the product detail page should show "(?P<product_name>[^"]*)"'))
def assert_detail_shows_product(product_detail_page, product_name):
    actual = product_detail_page.product_name()
    assert product_name in actual, f"Expected {product_name!r} in {actual!r}"


@then(parsers.re(r'the cart should contain the product "(?P<product_name>[^"]*)"'))
def assert_cart_contains_product(cart_page, product_name):
    assert cart_page.has_product(product_name), (
        f"Expected {product_name!r} in cart {cart_page.get_product_names()!r}"
    )


@then(parsers.re(r'the cart should contain "(?P<expected>[^"]*)"'))
def assert_cart_contains_text(cart_page, expected):
    row_text = cart_page.get_row_text("Blue Top")
    assert expected in row_text, f"Expected {expected!r} in row {row_text!r}"


@then("the cart should be empty")
def assert_cart_empty(cart_page):
    assert cart_page.is_empty(), "Expected the cart to be empty"


@then("I should not be logged in")
def assert_not_logged_in(nav_page):
    assert nav_page.is_logged_out(), "Unexpectedly still logged in"


@then("I should remain on the login page")
def assert_still_on_login(login_page):
    assert login_page.is_loaded(), "Expected to be on the login page"


@then(parsers.re(r'I should see the product price "(?P<expected_price>[^"]*)" in the results'))
def assert_product_price_in_results(products_page, expected_price):
    assert products_page.has_product("Blue Top"), (
        f"Expected 'Blue Top' in results {products_page.get_result_names()!r}"
    )
    names = products_page.get_result_names()
    assert any(expected_price in name for name in names), (
        f"Expected price {expected_price!r} among results {names!r}"
    )


@then("I should see no product results")
def assert_no_product_results(products_page):
    assert products_page.get_result_card_count() == 0, (
        "Expected zero product cards for a non-matching search"
    )
