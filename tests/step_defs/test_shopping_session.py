"""Step definitions for features/shopping_session.feature.

Binds the shopping-session scenarios to page-object methods only. No selectors
live here — every UI interaction goes through a page object. Presence is
asserted with waiting readers; absence with non-waiting probes.
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

@when(parsers.re(r'I log in as a "(?P<role>[^"]*)" user'))
def login_as_role(login_page, credentials, role):
    email, password = credentials(role)
    login_page.login_as(email, password)


@when("I go to the products page")
def go_to_products(nav_page):
    nav_page.open_products()


@when(parsers.parse('I search for "{term}"'))
def search_for_term(products_page, term):
    products_page.search_for(term)


@when(parsers.parse('I open the product "{product_name}" from the results'))
def open_product_from_results(products_page, product_name):
    products_page.open_product(product_name)


@when("I add the product to the cart")
def add_product_to_cart(product_detail_page):
    product_detail_page.add_to_cart()


@when("I view the cart from the modal")
def view_cart_from_modal(product_detail_page):
    product_detail_page.open_cart_from_modal()


@when(parsers.parse('I remove "{product_name}" from the cart'))
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
    assert nav_page.is_logged_out(), "Unexpectedly still logged in"


@then("I should see my account name in the navigation")
def assert_account_name_shown(nav_page):
    banner = nav_page.logged_in_name()
    assert "Logged in as" in banner, f"Expected a logged-in banner, got {banner!r}"


@then("the search results should be shown")
def assert_search_results_shown(products_page):
    products_page.wait_for_search_results()
    assert products_page.is_listing_loaded(), "Search results were not shown"


@then(parsers.parse('the product "{product_name}" should be listed with price "{price}"'))
def assert_product_listed_with_price(products_page, product_name, price):
    assert products_page.has_result(product_name), (
        f"Expected {product_name!r} in results, got {products_page.get_result_names()!r}"
    )
    card_text = products_page.get_card_text(product_name)
    assert price in card_text, f"Expected price {price!r} in card {card_text!r}"


@then(parsers.parse('the product detail page should show "{product_name}"'))
def assert_detail_shows_product(product_detail_page, product_name):
    assert product_detail_page.is_loaded(), "Product detail page did not load"
    actual = product_detail_page.product_name()
    assert product_name in actual, f"Expected {product_name!r}, got {actual!r}"


@then(parsers.parse('the cart should contain "{product_name}" with price "{price}"'))
def assert_cart_contains_product(cart_page, product_name, price):
    assert cart_page.is_loaded(), "Cart page did not load"
    assert cart_page.has_product(product_name), (
        f"Expected {product_name!r} in cart, got {cart_page.get_product_names()!r}"
    )
    row_text = cart_page.get_product_row_text(product_name)
    assert price in row_text, f"Expected price {price!r} in row {row_text!r}"


@then("the cart should be empty")
def assert_cart_empty(cart_page):
    cart_page.wait_until_empty()
    assert cart_page.is_cart_empty(), "Expected the cart to be empty"


@then("no product cards should be displayed")
def assert_no_product_cards(products_page):
    count = products_page.get_result_card_count()
    assert count == 0, f"Expected zero product cards, got {count}"
