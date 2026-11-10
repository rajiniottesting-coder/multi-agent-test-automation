"""Step definitions for features/cart_persistence.feature.

Covers SCRUM-368 (product survives sign-out/in), SCRUM-369 (removal persists),
and SCRUM-370 (removing every row shows the empty-cart message).

Conventions followed from the reference suite:
- Declare every step the feature uses in THIS module (steps are module-scoped).
- Call page-object methods only; no selectors here.
- Log in by ROLE via the `credentials` fixture.
- Assert PRESENCE with a waiting reader, ABSENCE with a non-waiting probe.

Persistent-state note (the cart page is `persistent_state: true`): the cart is
kept against the signed-in registered account and survives logout and the run.
This application declares no way to establish a clean start, so SCRUM-368 and
SCRUM-369 assert RELATIVELY - that the row this scenario added is present, or
is gone - which holds whatever the account started with. SCRUM-370 removes
EVERY row itself, so it owns a known end state and may assert the absolute
empty-cart message.

Reused Then sentences ("I should be logged in", "I should see my account name
in the navigation") are redeclared here because pytest-bdd steps are
module-scoped, and each asserts EXACTLY what the committed definition in
tests/step_defs/test_login.py asserts - nothing added.
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
def open_product_detail(products_page, base_url, product_name):
    products_page.open_product_detail_from_listing(base_url, product_name)


@when("I add the product to the cart")
def add_product_to_cart(product_detail_page):
    product_detail_page.add_to_cart()


@when("I view the cart from the confirmation modal")
def view_cart_from_modal(product_detail_page):
    product_detail_page.view_cart()


@when("I click the logout link")
def click_logout(nav_page):
    nav_page.logout()


@when("I open the cart page")
def open_cart_page(cart_page, base_url):
    cart_page.open_cart(base_url)


@when(parsers.parse('I remove the "{product_name}" row from the cart'))
def remove_product_row(cart_page, product_name):
    cart_page.remove_product(product_name)


@when("I remove every row from the cart")
def remove_every_row(cart_page):
    cart_page.remove_all_products()


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


@then("I should not see my account name in the navigation")
def assert_account_name_not_shown(nav_page):
    """Non-waiting probe: the waiting reader would time out rather than
    return False, so the assertion would never be reached."""
    assert not nav_page.is_logged_in(), "Unexpectedly still logged in"


@then(parsers.parse('the product name shown should be "{expected_name}"'))
def assert_product_name(product_detail_page, expected_name):
    actual = product_detail_page.product_name()
    assert expected_name.casefold() in actual.casefold(), (
        f"Expected product name {expected_name!r} in {actual!r}"
    )


@then(parsers.parse('the product price shown should be "{expected_price}"'))
def assert_product_price(product_detail_page, expected_price):
    actual = product_detail_page.product_price()
    assert expected_price.casefold() in actual.casefold(), (
        f"Expected product price {expected_price!r} in {actual!r}"
    )


@then(parsers.parse('the cart should contain a row for "{product_name}"'))
def assert_cart_has_row(cart_page, product_name):
    """RELATIVE presence check: the row this scenario added is there,
    whatever else the persistent cart already held."""
    cart_page.wait_for_product(product_name, present=True)


@then(parsers.parse('the cart should not contain a row for "{product_name}"'))
def assert_cart_missing_row(cart_page, product_name):
    """RELATIVE absence check: the row this scenario removed is gone,
    whatever else the persistent cart still holds."""
    cart_page.wait_for_product(product_name, present=False)


@then(parsers.parse('the "{product_name}" row should not be shown in the cart'))
def assert_named_row_not_shown(cart_page, product_name):
    cart_page.wait_for_product(product_name, present=False)


@then("the cart should show the empty-cart message")
def assert_cart_empty(cart_page):
    """Absolute emptiness is safe here only because this scenario removed
    EVERY row itself, so it owns the end state."""
    assert cart_page.is_empty(), "Expected the empty-cart message to be shown"
