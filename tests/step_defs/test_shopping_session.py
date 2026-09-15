"""Step definitions for features/shopping_session.feature.

Binds the shopping-session feature to page-object methods only. No selectors,
no raw page calls. Real login goes through the ROLE via the credentials
fixture; the search terms are literal test data.

Presence is asserted with waiting readers; absence with non-waiting probes.
Cart membership is asserted RELATIVELY (the product this test added is present
after adding, gone after removing), because the shared account's cart is not
guaranteed to start empty.
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
    products_page.open_products(base_url)


# ─────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────

@when(parsers.re(r'I log in as a "(?P<role>[^"]*)" user$'))
def login_as_role(login_page, credentials, role):
    """Log in with real credentials resolved from the environment."""
    email, password = credentials(role)
    login_page.login_as(email, password)


@when(parsers.re(r'I search for "(?P<term>[^"]*)"'))
def search_for(products_page, term):
    """Literal search term (may be empty for the full-catalogue edge case)."""
    products_page.search_for(term)


@when(parsers.re(r'I view the product "(?P<product_name>[^"]*)"'))
def view_product(products_page, product_name):
    products_page.view_product(product_name)


@when("I add the displayed product to the cart")
def add_displayed_product(product_detail_page):
    product_detail_page.add_to_cart()


@when("I view the cart from the added-to-cart modal")
def view_cart_from_modal(product_detail_page):
    product_detail_page.view_cart_from_modal()


@when(parsers.re(r'I remove "(?P<product_name>[^"]*)" from the cart'))
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
    """Non-waiting probe. The waiting reader would time out rather than
    return False, so the assertion would never be reached."""
    assert not nav_page.is_logged_in(), "Unexpectedly logged in"


@then("I should see my account name in the navigation")
def assert_account_name_shown(nav_page):
    banner = nav_page.logged_in_name()
    assert "Logged in as" in banner, f"Expected a logged-in banner, got {banner!r}"


@then(parsers.re(r'the search results should include the product "(?P<product_name>[^"]*)"'))
def assert_search_includes(products_page, product_name):
    assert products_page.has_result(product_name), (
        f"Expected {product_name!r} in the search results, "
        f"got {products_page.get_result_names()!r}"
    )


@then("the search results should be empty")
def assert_search_empty(products_page):
    assert products_page.get_result_count() == 0, (
        f"Expected zero result cards, got {products_page.get_result_count()}"
    )


@then(parsers.re(r'I should be on the product detail page for "(?P<product_name>[^"]*)"'))
def assert_on_product_detail(product_detail_page, product_name):
    assert product_detail_page.is_loaded(), "Product detail page did not load"
    actual = product_detail_page.product_name()
    assert product_name in actual, f"Expected {product_name!r} in {actual!r}"


@then(parsers.re(r'the cart should contain a row for "(?P<product_name>[^"]*)"'))
def assert_cart_contains(cart_page, product_name):
    cart_page.wait_for_product_row(product_name)


@then(parsers.re(r'the cart should no longer contain a row for "(?P<product_name>[^"]*)"'))
def assert_cart_absent(cart_page, product_name):
    cart_page.wait_for_product_row_absent(product_name)
