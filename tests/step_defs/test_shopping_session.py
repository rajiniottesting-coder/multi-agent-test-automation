"""Step definitions for features/shopping_session.feature.

Binds the shopping-session scenarios to page-object methods only. No selector
strings live here — every UI interaction goes through a page object.

Conventions copied from the reference login step defs:
- Declare EVERY step the feature uses in THIS module (steps are module-scoped,
  so a step defined elsewhere is invisible here). Re-declaring a step another
  module also declares is safe and expected.
- Call page-object methods only. Never put a selector in a step definition.
- Log in by ROLE via the `credentials` fixture; invalid/empty values stay
  literal because they are test data, not secrets.
- Use parsers.re with [^"]* where a quoted value could be empty; parsers.parse
  cannot match "".
- Assert PRESENCE with a waiting reader and ABSENCE with a non-waiting probe.
"""
from pytest_bdd import given, when, then, parsers, scenarios

from config.paths import feature_path

scenarios(str(feature_path("shopping_session")))


# ─────────────────────────────────────────────────────────────
# Given / When — navigation to a starting page
# ─────────────────────────────────────────────────────────────

@given("I am on the signup and login page")
@when("I am on the signup and login page")
def open_login_page(login_page, base_url):
    login_page.open_login_page(base_url)


@given("I am on the products page")
def open_products_page_given(products_page, base_url):
    products_page.open_products_page(base_url)


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
    """Literal values, for invalid and empty-field scenarios."""
    login_page.login_as(email, password)


@when("I log out")
def logout(nav_page):
    nav_page.logout()


# ─────────────────────────────────────────────────────────────
# When — searching and browsing products
# ─────────────────────────────────────────────────────────────

@when(parsers.re(r'I search for "(?P<term>[^"]*)" on the products page'))
def search_products(products_page, base_url, term):
    products_page.open_products_page(base_url)
    products_page.search_for(term)


@when(parsers.re(r'I open the product "(?P<name>[^"]*)" from the results'))
def open_product_from_results(products_page, name):
    products_page.open_product_named(name)


@when("I add the product to the cart")
def add_product_to_cart(product_detail_page):
    product_detail_page.add_product_to_cart()


@when("I view the cart from the modal")
def view_cart_from_modal(product_detail_page):
    product_detail_page.view_cart_from_modal()


@when("I continue shopping from the modal")
def continue_shopping_from_modal(product_detail_page):
    product_detail_page.continue_shopping_from_modal()


@when("I open the cart page")
def open_cart_page(cart_page, base_url):
    cart_page.open_cart_page(base_url)


@when(parsers.re(r'I remove "(?P<name>[^"]*)" from the cart'))
def remove_from_cart(cart_page, name):
    cart_page.remove_product(name)


# ─────────────────────────────────────────────────────────────
# Then — authentication state
# ─────────────────────────────────────────────────────────────

@then("I should be logged in")
def assert_logged_in(nav_page):
    assert nav_page.wait_until_logged_in(), "No session after logging in"


@then("I should not be logged in")
def assert_not_logged_in(nav_page):
    """Non-waiting probe — the waiting reader would time out rather than
    return False, so the assertion would never be reached."""
    assert not nav_page.is_logged_in(), "Unexpectedly logged in"


@then("I should see my account name in the navigation")
def assert_account_name_shown(nav_page):
    banner = nav_page.logged_in_name()
    assert "Logged in as" in banner, f"Expected a logged-in banner, got {banner!r}"


@then("the login attempt should be rejected")
def assert_login_rejected(nav_page):
    """The invalid-credential variants must not authenticate the user. Some
    variants show an error, some are blocked by native validation — in every
    case the reliable, shared signal is that no session exists."""
    assert not nav_page.is_logged_in(), "Login attempt unexpectedly succeeded"


@then("I should be back on the login page")
def assert_back_on_login(login_page):
    assert login_page.is_loaded(), "Expected to be back on the login page"


# ─────────────────────────────────────────────────────────────
# Then — search results
# ─────────────────────────────────────────────────────────────

@then("the search results should be shown")
def assert_search_results_shown(products_page):
    assert products_page.is_search_executed(), "Search did not execute"


@then(parsers.re(r'I should see a product named "(?P<name>[^"]*)" in the results'))
def assert_product_in_results(products_page, name):
    assert products_page.has_product_named(name), f"Product {name!r} not in results"


@then("no product result cards should be displayed")
def assert_no_result_cards(products_page):
    """Empty search renders NO cards rather than an empty-state message, so
    absence is asserted by an exact zero count."""
    assert products_page.get_result_card_count() == 0, "Expected zero result cards"


# ─────────────────────────────────────────────────────────────
# Then — product detail
# ─────────────────────────────────────────────────────────────

@then(parsers.re(r'the product detail page should show the name "(?P<name>[^"]*)"'))
def assert_detail_name(product_detail_page, name):
    actual = product_detail_page.product_detail_name()
    assert actual == name, f"Expected detail name {name!r}, got {actual!r}"


@then("I should see the add-to-cart confirmation modal")
def assert_added_modal(product_detail_page):
    assert product_detail_page.is_added_modal_shown(), "Add-to-cart modal not shown"


# ─────────────────────────────────────────────────────────────
# Then — cart contents
# ─────────────────────────────────────────────────────────────

@then(parsers.re(r'the cart should contain a row for "(?P<name>[^"]*)"'))
def assert_cart_has_row(cart_page, name):
    assert cart_page.has_product_row(name), f"Cart has no row for {name!r}"


@then(parsers.re(r'the cart should no longer contain a row for "(?P<name>[^"]*)"'))
def assert_cart_row_removed(cart_page, name):
    cart_page.wait_until_product_removed(name)
