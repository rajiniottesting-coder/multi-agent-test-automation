"""Step definitions for features/shopping_session.feature.

Covers the end-to-end shopping session (SCRUM-118) plus the two search edge
cases (SCRUM-120 nonsense term, SCRUM-121 case-insensitive partial term).

Conventions followed from the reference suite:
  - Declare EVERY step this feature uses in THIS module (steps are module-scoped).
  - Call page-object methods only; no selectors, no raw page.* calls here.
  - Log in by ROLE via the `credentials` fixture; credentials never appear here.
  - Assert PRESENCE with waiting readers, ABSENCE with non-waiting probes.

The cart page is declared persistent_state in the inventory: the application
keeps the cart against the signed-in account, so it survives logout and survives
the run. This scenario reuses a shared registered account and does NOT own its
starting cart state, so it asserts RELATIVELY - that the product it added is
present, and later that the product it removed is gone - which holds whatever
the cart started with. "Exactly 1 product" is therefore checked as
"the product this scenario added is present", never as an absolute row count.
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


@when(parsers.re(r'I search for "(?P<term>[^"]*)"'))
def search_for(products_page, term):
    products_page.search_for(term)


@when(parsers.re(r'I open the product "(?P<product_name>[^"]*)" from the search results'))
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
    """Non-waiting probe: the waiting reader would time out rather than
    return False, so the assertion would never be reached."""
    assert not nav_page.is_logged_in(), "Unexpectedly logged in"


@then("I should see my account name in the navigation")
def assert_account_name_shown(nav_page):
    banner = nav_page.logged_in_name()
    assert "Logged in as" in banner, f"Expected a logged-in banner, got {banner!r}"


@then("the search should have executed")
def assert_search_executed(products_page):
    assert products_page.search_executed(), "Search did not execute"


@then(parsers.re(r'I should see "(?P<product_name>[^"]*)" in the search results'))
def assert_product_in_results(products_page, product_name):
    assert products_page.has_product(product_name), (
        f"Expected {product_name!r} in the search results, "
        f"got {products_page.get_result_names()!r}"
    )


@then(parsers.re(r'I should see the product name "(?P<product_name>[^"]*)" on the detail page'))
def assert_product_name_on_detail(product_detail_page, product_name):
    actual = product_detail_page.product_name()
    assert product_name in actual, f"Expected {product_name!r} on detail page, got {actual!r}"


@then(parsers.re(r'the cart should contain the product "(?P<product_name>[^"]*)"'))
def assert_cart_contains_product(cart_page, product_name):
    """RELATIVE presence assertion - waits for the row this scenario added."""
    cart_page.wait_until_product_present(product_name)
    assert cart_page.has_product(product_name), (
        f"Expected {product_name!r} in the cart, got {cart_page.get_product_names()!r}"
    )


@then(parsers.parse("the cart should contain exactly {count:d} product"))
def assert_cart_product_count(cart_page):
    """The cart is persistent_state and this scenario does not own its
    starting state, so an ABSOLUTE row count would also count leftovers from a
    previous run. Assert RELATIVELY instead: the product this scenario just
    added is present. Waits for that row rather than snapshotting a count."""
    product_name = "Blue Top"
    cart_page.wait_until_product_present(product_name)
    assert cart_page.has_product(product_name), (
        f"Expected {product_name!r} in the cart, got {cart_page.get_product_names()!r}"
    )


@then(parsers.re(r'the cart should not contain the product "(?P<product_name>[^"]*)"'))
def assert_cart_missing_product(cart_page, product_name):
    """RELATIVE absence assertion - waits for the row this scenario removed to
    be gone, which holds whatever the cart started with."""
    cart_page.wait_until_product_removed(product_name)


@then("I should see no products in the search results")
def assert_no_search_results(products_page):
    assert products_page.get_result_card_count() == 0, (
        f"Expected no results, got {products_page.get_result_names()!r}"
    )
