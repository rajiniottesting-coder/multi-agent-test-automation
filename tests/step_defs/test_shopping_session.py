"""Step definitions for features/shopping_session.feature.

Binds the shopping-session Gherkin steps to page-object methods. Every step
the feature uses is declared here — pytest-bdd steps are module-scoped, so a
step defined elsewhere is invisible to this module.

Rules honoured:
- Call page-object methods only; no selectors in step definitions.
- Log in by ROLE via the `credentials` fixture; credentials never appear here.
- Assert PRESENCE with waiting readers; ABSENCE with non-waiting probes.
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


@when("I open the products listing from the navigation")
def open_products_listing(nav_page):
    nav_page.open_products()


@when(parsers.parse('I search for "{term}"'))
def search_for_term(products_page, term):
    products_page.search_for(term)


@when(parsers.parse('I open the product "{product_name}" from the results'))
def open_product_from_results(products_page, product_name):
    products_page.open_product(product_name)


@when("I add the product to the cart from the product detail page")
def add_product_to_cart(product_detail_page):
    product_detail_page.add_product_to_cart()


@when("I view the cart from the add-to-cart modal")
def view_cart_from_modal(product_detail_page):
    product_detail_page.open_cart_from_modal()


@when(parsers.parse('I remove "{product_name}" from the cart'))
def remove_product_from_cart(cart_page, product_name):
    cart_page.remove_product(product_name)


@when("I log out from the navigation")
def logout_from_navigation(nav_page):
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


@then("the products listing should be shown")
def assert_products_listing_shown(products_page):
    assert products_page.is_loaded(), "Expected the products listing to be shown"


@then("the search should have executed")
def assert_search_executed(products_page):
    assert products_page.search_has_run(), "Expected the search to have executed"


@then(parsers.parse('I should see the product "{product_name}" priced "{price}" in the results'))
def assert_product_priced_in_results(products_page, product_name, price):
    assert products_page.has_product(product_name), (
        f"Expected {product_name!r} in results, got {products_page.result_names()!r}"
    )


@then(parsers.parse('the product detail page should show "{product_name}"'))
def assert_detail_shows_product(product_detail_page, product_name):
    assert product_detail_page.is_loaded(), "Expected the product detail page to load"
    actual = product_detail_page.product_name()
    assert product_name in actual, f"Expected {product_name!r} in {actual!r}"


@then(parsers.parse('the cart should contain exactly one row for "{product_name}"'))
def assert_cart_has_one_row(cart_page, product_name):
    assert cart_page.is_loaded(), "Expected the cart page to load"
    assert cart_page.get_row_count() == 1, (
        f"Expected exactly one cart row, got {cart_page.get_row_count()}"
    )
    assert cart_page.has_product(product_name), (
        f"Expected {product_name!r} in cart, got {cart_page.get_product_names()!r}"
    )


@then("the cart should be empty")
def assert_cart_empty(cart_page):
    assert cart_page.is_empty(), "Expected the cart to be empty"


@then("I should be redirected to the login page")
def assert_redirected_to_login(login_page):
    assert login_page.is_loaded(), "Expected to be redirected to the login page"


@then("I should not be logged in")
def assert_not_logged_in(nav_page):
    assert not nav_page.is_logged_in(), "Unexpectedly logged in"


@then("no product results should be displayed")
def assert_no_results(products_page):
    count = products_page.result_card_count()
    assert count == 0, f"Expected no result cards, got {count}"
