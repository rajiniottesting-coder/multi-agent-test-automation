"""Step definitions for features/shopping_session.feature.

Binds the shopping-session scenarios to the login, nav, products,
product-detail and cart page objects. Selectors never appear here — every
UI interaction goes through a page-object method. Real logins go through a
ROLE resolved by the `credentials` fixture; invalid data stays literal.
"""
from pytest_bdd import given, when, then, parsers, scenarios

from config.paths import feature_path

scenarios(str(feature_path("shopping_session")))


# ─────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────

@given("I am on the home page")
def open_home_page(login_page, base_url):
    """The session starts signed out. Reaching the login page is the concrete
    landing this scenario needs before clicking through to sign in, and
    LoginPage.open_login_page is the confirmed navigation available here."""
    login_page.open_login_page(base_url)


@given("I am on the signup and login page")
def open_login_page(login_page, base_url):
    login_page.open_login_page(base_url)


@given("I should see the login and signup link")
def given_see_signup_login_link(nav_page):
    assert nav_page.wait_until_logged_out(), "Expected the Signup / Login link"


# ─────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────

@when("I go to the signup and login page")
def go_to_signup_login(login_page, base_url):
    """Navigate to the Signup / Login screen via its own page object, which
    confirms arrival on that page."""
    login_page.open_login_page(base_url)


@when(parsers.re(r'I log in as a "(?P<role>[^"]*)" user$'))
def login_as_role(login_page, credentials, role):
    email, password = credentials(role)
    login_page.login_as(email, password)


@when(parsers.re(r'I log in with email "(?P<email>[^"]*)" and password "(?P<password>[^"]*)"'))
def login_with_literal_credentials(login_page, email, password):
    login_page.login_as(email, password)


@when("I go to the products page")
def go_to_products(products_page, base_url):
    products_page.open_listing(base_url)


@when(parsers.parse('I search for "{term}"'))
def search_for_term(products_page, term):
    products_page.search_for(term)


@when(parsers.parse('I view the product "{product_name}"'))
def view_product(products_page, product_name):
    products_page.view_product(product_name)


@when("I add the product to the cart")
def add_product_to_cart(product_detail_page):
    product_detail_page.add_to_cart()


@when("I go to the cart from the confirmation modal")
def go_to_cart_from_modal(product_detail_page):
    product_detail_page.go_to_cart_from_modal()


@when(parsers.parse('I remove "{product_name}" from the cart'))
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


@then("I should see my account name in the navigation")
def assert_account_name_shown(nav_page):
    banner = nav_page.logged_in_name()
    assert "Logged in as" in banner, f"Expected a logged-in banner, got {banner!r}"


@then("the search results should be shown")
def assert_search_results_shown(products_page):
    assert products_page.search_results_shown(), "Expected the searched-results view"


@then(parsers.parse('a product card for "{product_name}" should be present'))
def assert_product_card_present(products_page, product_name):
    assert products_page.has_product_card(product_name), \
        f"Expected a product card for {product_name!r}"


@then(parsers.parse('the product detail page should show "{product_name}"'))
def assert_detail_shows(product_detail_page, product_name):
    actual = product_detail_page.get_product_name()
    assert product_name in actual, f"Expected {product_name!r} in {actual!r}"


@then("I should see the product added confirmation")
def assert_added_confirmation(product_detail_page):
    assert product_detail_page.has_added_confirmation(), \
        "Expected the product-added confirmation modal"


@then(parsers.parse('the cart should contain a row for "{product_name}"'))
def assert_cart_contains_row(cart_page, product_name):
    cart_page.wait_for_product_row(product_name)


@then(parsers.parse('the cart should not contain a row for "{product_name}"'))
def assert_cart_row_removed(cart_page, product_name):
    cart_page.wait_for_product_row_removed(product_name)


@then("I should see the login and signup link")
def then_see_signup_login_link(nav_page):
    assert nav_page.wait_until_logged_out(), "Expected the Signup / Login link"


@then("no product cards should be displayed")
def assert_no_product_cards(products_page):
    assert products_page.get_result_count() == 0, \
        "Expected no product cards for a term matching nothing"


@then(parsers.re(r'I should see the error message "(?P<expected_message>[^"]*)"'))
def assert_error_message(login_page, expected_message):
    actual = login_page.get_login_error()
    assert expected_message in actual, f"Expected {expected_message!r} in {actual!r}"


@then("I should remain on the login page")
def assert_still_on_login(login_page):
    assert login_page.is_loaded(), "Expected to stay on the login page"


@then("I should not be logged in")
def assert_not_logged_in(nav_page):
    assert not nav_page.is_logged_in(), "Unexpectedly logged in"
