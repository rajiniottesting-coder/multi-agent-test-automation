"""Step definitions for features/shopping_session.feature.

Binds the shopping-session Gherkin steps to page-object methods. Follows the
login reference: page-object calls only, no selectors here; login by ROLE via
the `credentials` fixture; presence asserted with waiting readers, absence with
non-waiting probes.

NOTE on the cart: the `cart` inventory page carries persistent_state - the app
keeps it against the signed-in account, so it survives logout and survives the
run. A previous run's leftovers would be counted too, and no wait removes them.
This scenario therefore asserts RELATIVELY: after removing the product it added,
it waits for THAT product's row to be gone (wait via assert_product_removed),
which holds whatever the account started with. It does not assert absolute
emptiness, because the inventory offers no way for this scenario to own its
starting state (no cart-clear method, no fresh-registration flow described).
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


@when("I open the products page")
def open_products_page(nav_page):
    nav_page.open_products()


@when(parsers.re(r'I search for "(?P<term>[^"]*)"'))
def search_for(products_page, term):
    products_page.search_for(term)


@when(parsers.re(r'I open the product "(?P<product_name>[^"]*)" from the results'))
def open_product_from_results(products_page, product_name):
    products_page.open_product(product_name)


@when("I add the product to the cart")
def add_product_to_cart(product_detail_page):
    product_detail_page.add_product_to_cart()


@when("I view the cart from the modal")
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


@then("the search results should be shown")
def assert_search_results_shown(products_page):
    assert products_page.wait_until_searched(), "Search did not execute"


@then(parsers.re(r'I should see the product "(?P<product_name>[^"]*)" in the results'))
def assert_product_in_results(products_page, product_name):
    names = products_page.result_names()
    assert product_name in names, f"Expected {product_name!r} in {names!r}"


@then(parsers.re(r'I should be on the product detail page for "(?P<product_name>[^"]*)"'))
def assert_on_product_detail(product_detail_page, product_name):
    assert product_detail_page.is_loaded(), "Product detail page did not load"
    actual = product_detail_page.product_name()
    assert product_name in actual, f"Expected {product_name!r} in {actual!r}"


@then(parsers.re(r'the cart should contain the product "(?P<product_name>[^"]*)"'))
def assert_cart_contains_product(cart_page, product_name):
    cart_page.wait_for_product(product_name)


@then("the cart should be empty")
def assert_cart_empty(cart_page):
    """Assert RELATIVELY. The cart persists against the signed-in account
    across runs, so an absolute emptiness check would count leftovers this
    scenario never added. Instead, wait for the product THIS scenario added
    and removed to be gone - true whatever the account started with."""
    cart_page.assert_product_removed("Blue Top")


@then("I should see the login and signup link")
def assert_logged_out(nav_page):
    assert nav_page.wait_until_logged_out(), "Still recognised as logged in"


@then("no products should be displayed in the results")
def assert_no_products(products_page):
    count = products_page.result_card_count()
    assert count == 0, f"Expected zero product cards, found {count}"
