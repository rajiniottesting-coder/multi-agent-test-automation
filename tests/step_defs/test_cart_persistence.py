"""Step definitions for features/cart_persistence.feature.

Cart persistence across sign-out and sign-in for a registered shopper.

Conventions (see pages/login_page.py and tests/step_defs/test_login.py):
  - call page-object methods only; no selectors in step definitions
  - log in by ROLE via the `credentials` fixture
  - assert presence with waiting readers, absence with non-waiting probes
  - every feature step has exactly one matching decorator here
"""
from pytest_bdd import given, when, then, parsers, scenarios

from config.paths import feature_path

scenarios(str(feature_path("cart_persistence")))


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


@when(parsers.parse('I open the product detail page for "{product_name}"'))
def open_product_detail_page(products_page, product_detail_page, base_url, product_name):
    products_page.open_products(base_url)
    products_page.open_product_detail_page(product_name)


@when("I add the product to the cart and view the cart")
def add_to_cart_and_view_cart(product_detail_page):
    product_detail_page.add_to_cart_and_view_cart()


@when("I log out")
def log_out(nav_page):
    nav_page.logout()


@when("I navigate to the cart page")
def navigate_to_cart(cart_page, base_url):
    cart_page.open_cart(base_url)


@when(parsers.parse('I remove "{product_name}" from the cart'))
def remove_product(cart_page, product_name):
    cart_page.remove_product(product_name)


@when("I remove every product from the cart")
def remove_every_product(cart_page):
    cart_page.remove_all_products()


# ─────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────

@then("I should see my account name in the navigation")
def assert_account_name_shown(nav_page):
    banner = nav_page.logged_in_name()
    assert "Logged in as" in banner, f"Expected a logged-in banner, got {banner!r}"


@then(parsers.parse('I should see the product name "{product_name}"'))
def assert_product_name(product_detail_page, product_name):
    actual = product_detail_page.product_name()
    assert product_name.casefold() in actual.casefold(), (
        f"Expected product name {product_name!r} in {actual!r}"
    )


@then(parsers.parse('I should see the product price "{product_price}"'))
def assert_product_price(product_detail_page, product_price):
    actual = product_detail_page.product_price()
    assert product_price.casefold() in actual.casefold(), (
        f"Expected product price {product_price!r} in {actual!r}"
    )


@then(parsers.parse('the cart should contain a row for "{product_name}"'))
def assert_cart_contains_row(cart_page, product_name):
    cart_page.wait_for_product(product_name, present=True)
    assert cart_page.has_product(product_name), (
        f"Expected a cart row for {product_name!r}"
    )


@then(parsers.parse('the cart should not contain a row for "{product_name}"'))
def assert_cart_missing_row(cart_page, product_name):
    cart_page.wait_for_product(product_name, present=False)


@then("I should remain on the login page")
def assert_still_on_login(login_page):
    assert login_page.is_loaded(), "Expected to stay on the login page"


@then("the logout link should not be shown in the navigation")
def assert_logout_link_absent(nav_page):
    """Non-waiting probe. The Logout link is CONDITIONAL - present only while
    authenticated - so its absence is answered immediately, never by waiting."""
    assert not nav_page.is_logged_in(), "Logout link is still shown in the navigation"


@then("no product rows should be shown in the cart")
def assert_no_product_rows(cart_page):
    assert cart_page.is_empty(), "Expected no product rows in the cart"


@then("the cart should show the empty-cart message")
def assert_cart_empty(cart_page):
    assert cart_page.is_empty(), "Expected the empty-cart message to be shown"
