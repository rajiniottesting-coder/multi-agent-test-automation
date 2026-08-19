"""Step definitions for features/shopping_session.feature.

Binds every Gherkin step in the shopping-session feature to page-object
methods. Steps are module-scoped in pytest-bdd, so every phrase the feature
uses is declared here even where it duplicates another module's step.

Rules followed:
  - Page-object methods only; no selectors in this file.
  - Log in by ROLE via the `credentials` fixture; invalid/empty values stay
    literal because they are test data, not secrets.
  - parsers.re with [^"]* where a quoted value may be empty ("").
  - Presence asserted with waiting readers; absence with non-waiting probes.
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
    email, password = credentials(role)
    login_page.login_as(email, password)


@when(parsers.re(r'I log in as a "(?P<role>[^"]*)" user with an incorrect password'))
def login_as_role_wrong_password(login_page, credentials, role):
    email, _ = credentials(role)
    login_page.login_as(email, "WrongPass!123")


@when(parsers.re(r'I log in with email "(?P<email>[^"]*)" and password "(?P<password>[^"]*)"'))
def login_with_literal_credentials(login_page, email, password):
    login_page.login_as(email, password)


@when("I clear the credential fields")
def clear_credentials(login_page):
    login_page.clear_credentials()


@when("I go to the products page")
def go_to_products(nav_page):
    nav_page.go_to_products()


@when(parsers.parse('I search for the product "{term}"'))
def search_for_product(products_page, term):
    products_page.search_for(term)


@when(parsers.parse('I open the product "{product_name}"'))
def open_product(products_page, product_name):
    products_page.open_product(product_name)


@when("I add the product to the cart")
def add_product_to_cart(product_detail_page):
    product_detail_page.add_product_to_cart()


@when("I view the cart from the modal")
def view_cart_from_modal(product_detail_page):
    product_detail_page.view_cart_from_modal()


@when(parsers.parse('I remove the product "{product_name}" from the cart'))
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
    assert not nav_page.is_logged_in(), "Unexpectedly logged in"


@then("I should see my account name in the navigation")
def assert_account_name_shown(nav_page):
    banner = nav_page.logged_in_name()
    assert "Logged in as" in banner, f"Expected a logged-in banner, got {banner!r}"


@then("the search results should be displayed")
def assert_search_results_displayed(products_page):
    assert products_page.has_search_executed(), "Search does not appear to have executed"


@then(parsers.parse('the product "{product_name}" should be shown with price "{price}"'))
def assert_product_shown_with_price(products_page, product_name, price):
    assert products_page.has_product(product_name), \
        f"Expected {product_name!r} in results, got {products_page.get_product_names()!r}"
    actual_price = products_page.get_price_for_product(product_name)
    assert price in actual_price, \
        f"Expected price {price!r} for {product_name!r}, got {actual_price!r}"


@then(parsers.parse('the product detail page should show the product name "{product_name}"'))
def assert_detail_product_name(product_detail_page, product_name):
    actual = product_detail_page.product_name()
    assert product_name in actual, \
        f"Expected product name {product_name!r}, got {actual!r}"


@then(parsers.parse('the cart should contain exactly one row for "{product_name}"'))
def assert_cart_one_row(cart_page, product_name):
    assert cart_page.is_loaded(), "Cart did not load"
    assert cart_page.has_product(product_name), \
        f"Expected {product_name!r} in cart, got {cart_page.get_product_names()!r}"
    count = cart_page.get_row_count()
    assert count == 1, f"Expected exactly one cart row, got {count}"


@then(parsers.parse('the cart row for "{product_name}" should show price "{price}" and quantity "{quantity}"'))
def assert_cart_row_price_and_quantity(cart_page, product_name, price, quantity):
    row_text = cart_page.get_row_text_for(product_name)
    assert price in row_text, f"Expected price {price!r} in row, got {row_text!r}"
    assert quantity in row_text, f"Expected quantity {quantity!r} in row, got {row_text!r}"


@then("the cart should be empty")
def assert_cart_empty(cart_page):
    assert cart_page.is_empty(), "Expected the cart to be empty"


@then("I should remain on the login page")
def assert_still_on_login(login_page):
    assert login_page.is_loaded(), "Expected to stay on the login page"


@then(parsers.re(r'I should see the error message "(?P<expected_message>[^"]*)"'))
def assert_error_message(login_page, expected_message):
    actual = login_page.get_login_error()
    assert expected_message in actual, f"Expected {expected_message!r} in {actual!r}"


@then("the login or signup link should be present in the navigation")
def assert_login_signup_link_present(nav_page):
    assert not nav_page.is_logged_in(), \
        "Expected the Login/Signup link, but a session is still active"


@then("no product cards should be displayed in the results")
def assert_no_product_cards(products_page):
    count = products_page.get_card_count()
    assert count == 0, f"Expected zero product cards, got {count}"
