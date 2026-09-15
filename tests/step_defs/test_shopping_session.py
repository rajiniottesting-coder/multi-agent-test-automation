"""Step definitions for features/shopping_session.feature.

Covers three scenarios from the shopping-session story:
  - SCRUM-177: empty search returns the full catalogue
  - SCRUM-176: nonexistent search term returns zero cards
  - SCRUM-174: full session — login, search, add, verify, remove, logout

Rules honoured here:
  - Call page-object methods only; no selectors in step definitions.
  - Log in by ROLE via the `credentials` fixture; no literal credentials.
  - Assert PRESENCE with waiting readers, ABSENCE with non-waiting probes.
  - Cart membership is asserted RELATIVELY (present after add, gone after
    remove), because the shared account's cart is not guaranteed empty.
"""
from pytest_bdd import given, when, then, parsers, scenarios

from config.paths import feature_path

scenarios(str(feature_path("shopping_session")))


# ─────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────

@given("I am on the products page")
def open_products_page(products_page, base_url):
    products_page.open_listing(base_url)


@given("I am on the signup and login page")
def open_login_page(login_page, base_url):
    login_page.open_login_page(base_url)


# ─────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────

@when("I submit the search without entering a term")
def submit_empty_search(products_page):
    products_page.submit_search_empty()


@when(parsers.parse('I search for "{term}"'))
def search_for_term(products_page, term):
    products_page.search_for(term)


@when(parsers.re(r'I log in as a "(?P<role>[^"]*)" user$'))
def login_as_role(login_page, credentials, role):
    email, password = credentials(role)
    login_page.login_as(email, password)


@when("I go to the products page")
def go_to_products_page(products_page, base_url):
    products_page.open_listing(base_url)


@when(parsers.parse('I view the product "{product_name}"'))
def view_product(products_page, product_name):
    products_page.view_product(product_name)


@when("I add the product to the cart")
def add_product_to_cart(product_detail_page):
    product_detail_page.add_product_to_cart()


@when("I view the cart from the added modal")
def view_cart_from_modal(product_detail_page):
    product_detail_page.view_cart_from_modal()


@when(parsers.parse('I remove "{product_name}" from the cart'))
def remove_from_cart(cart_page, product_name):
    cart_page.remove_product(product_name)


@when("I log out")
def log_out(nav_page):
    nav_page.logout()


# ─────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────

@then(parsers.parse('the search results should include "{product_name}"'))
def assert_results_include(products_page, product_name):
    assert products_page.has_result_named(product_name), (
        f"Expected {product_name!r} among the search results"
    )


@then("no product cards should be displayed")
def assert_no_product_cards(products_page):
    count = products_page.get_result_card_count()
    assert count == 0, f"Expected zero product cards, found {count}"


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


@then(parsers.parse('I should see the product name "{product_name}"'))
def assert_product_name(product_detail_page, product_name):
    actual = product_detail_page.product_name()
    assert actual == product_name, f"Expected {product_name!r}, got {actual!r}"


@then(parsers.parse('the cart should contain "{product_name}"'))
def assert_cart_contains(cart_page, product_name):
    assert cart_page.contains_product(product_name), (
        f"Expected the cart to contain {product_name!r}"
    )


@then(parsers.parse('the cart should not contain "{product_name}"'))
def assert_cart_not_contains(cart_page, product_name):
    cart_page.wait_until_product_removed(product_name)


@then("I should be on the login page")
def assert_on_login_page(login_page):
    assert login_page.is_loaded(), "Expected to be on the login page"
