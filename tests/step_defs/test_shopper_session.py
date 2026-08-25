"""Step definitions for features/shopper_session.feature.

Covers the full registered-shopper session (login, search, add to cart,
remove, logout), a failed-login negative case, and a nonexistent-product
search edge case.

Conventions (see reference test_login.py):
  - real logins go through the `credentials` fixture via a ROLE
  - invalid data (wrong password) stays literal — test data, not a secret
  - step definitions call page-object methods only; no selectors here
  - PRESENCE asserted with waiting readers, ABSENCE with non-waiting probes
"""
from pytest_bdd import given, when, then, parsers, scenarios

from config.paths import feature_path

scenarios(str(feature_path("shopper_session")))


# ─────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────

@given("I am on the signup and login page")
def open_login_page(login_page, base_url):
    login_page.open_login_page(base_url)


@given("I am on the products page")
def open_products_page(products_page, base_url):
    products_page.open_listing(base_url)


# ─────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────

@when(parsers.re(r'I log in as a "(?P<role>[^"]*)" user$'))
def login_as_role(login_page, credentials, role):
    """Log in with real credentials resolved from the environment."""
    email, password = credentials(role)
    login_page.login_as(email, password)


@when(parsers.re(r'I log in as a "(?P<role>[^"]*)" user with an incorrect password'))
def login_as_role_wrong_password(login_page, credentials, role):
    """Valid email, deliberately wrong password (test data, not a secret)."""
    email, _ = credentials(role)
    login_page.login_as(email, "WrongPass123!")


@when("I go to the products page")
def go_to_products_page(products_page, base_url):
    products_page.open_listing(base_url)


@when(parsers.parse('I search for "{term}"'))
def search_for_term(products_page, term):
    products_page.search_for(term)


@when(parsers.parse('I open the product "{product_name}" from the search results'))
def open_product_from_results(products_page, product_name):
    products_page.open_product(product_name)


@when("I add the product to the cart")
def add_product_to_cart(product_detail_page):
    product_detail_page.add_to_cart()


@when("I view the cart from the modal")
def view_cart_from_modal(product_detail_page):
    product_detail_page.view_cart_from_modal()


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
    """Non-waiting probe. The waiting reader would time out rather than
    return False, so the assertion would never be reached."""
    assert not nav_page.is_logged_in(), "Unexpectedly logged in"


@then("I should see my account name in the navigation")
def assert_account_name_shown(nav_page):
    banner = nav_page.logged_in_name()
    assert "Logged in as" in banner, f"Expected a logged-in banner, got {banner!r}"


@then(parsers.parse('the search results should include "{product_name}"'))
def assert_search_includes(products_page, product_name):
    assert products_page.has_result(product_name), (
        f"Expected {product_name!r} in the search results"
    )


@then(parsers.parse('I should be on the product detail page for "{product_name}"'))
def assert_on_product_detail(product_detail_page, product_name):
    actual = product_detail_page.product_name()
    assert product_name in actual, (
        f"Expected product detail for {product_name!r}, got {actual!r}"
    )


@then(parsers.parse('the cart should contain a row for "{product_name}"'))
def assert_cart_contains(cart_page, product_name):
    assert cart_page.has_product(product_name), (
        f"Expected a cart row for {product_name!r}"
    )


@then(parsers.parse('the cart should not contain a row for "{product_name}"'))
def assert_cart_not_contains(cart_page, product_name):
    """Waiting-for-absence: re-checks until the row is gone rather than
    reading the list once right after the removal."""
    cart_page.wait_for_product_row_absent(product_name)


@then(parsers.re(r'I should see the error message "(?P<expected_message>[^"]*)"'))
def assert_error_message(login_page, expected_message):
    actual = login_page.get_login_error()
    assert expected_message in actual, f"Expected {expected_message!r} in {actual!r}"


@then("I should remain on the login page")
def assert_still_on_login(login_page):
    assert login_page.is_loaded(), "Expected to stay on the login page"


@then("the search should return no product cards")
def assert_no_product_cards(products_page):
    assert products_page.search_executed(), "Search did not execute"
    assert products_page.get_result_card_count() == 0, (
        "Expected zero product cards for a nonexistent search term"
    )
