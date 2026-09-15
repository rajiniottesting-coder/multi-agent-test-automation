"""Step definitions for features/shopping_session.feature.

Covers SCRUM-174/175/176/177: a full shopping session, invalid-login variants,
and the two search edge cases. Follows the login.feature reference style:
- Every step the feature uses is declared HERE (steps are module-scoped).
- Step defs call page-object methods only; no selectors, no DOM access.
- Real logins go through the `credentials` fixture by ROLE; invalid data stays
  literal.
- parsers.re with [^"]* wherever a quoted value can be empty.
- Presence asserted with waiting readers; absence with non-waiting probes.
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
    products_page.submit_empty_search()


@when(parsers.re(r'I search for "(?P<term>[^"]*)"'))
def search_for_term(products_page, term):
    products_page.search_for(term)


@when(parsers.re(r'I log in with email "(?P<email>[^"]*)" and password "(?P<password>[^"]*)"'))
def login_with_literal_credentials(login_page, email, password):
    """Literal values, for the invalid and empty-field variants."""
    login_page.login_as(email, password)


@when("I clear the credential fields")
def clear_credentials(login_page):
    login_page.clear_credentials()


@when(parsers.re(r'I log in as a "(?P<role>[^"]*)" user with an incorrect password'))
def login_as_role_wrong_password(login_page, credentials, role):
    """Valid registered email, deliberately wrong password (test data)."""
    email, _ = credentials(role)
    login_page.login_as(email, "definitely-not-the-password")


@when(parsers.re(r'I log in as a "(?P<role>[^"]*)" user$'))
def login_as_role(login_page, credentials, role):
    """Log in with real credentials resolved from the environment."""
    email, password = credentials(role)
    login_page.login_as(email, password)


@when("I go to the products page")
def go_to_products_page(products_page, base_url):
    products_page.open_listing(base_url)


@when(parsers.re(r'I view the product "(?P<product_name>[^"]*)" from the results'))
def view_product_from_results(products_page, product_name):
    products_page.view_product(product_name)


@when("I add the product to the cart from the detail page")
def add_product_to_cart(product_detail_page):
    product_detail_page.add_product_to_cart()


@when("I view the cart from the added-to-cart modal")
def view_cart_from_modal(product_detail_page):
    product_detail_page.view_cart_from_modal()


@when(parsers.re(r'I remove "(?P<product_name>[^"]*)" from the cart'))
def remove_from_cart(cart_page, product_name):
    cart_page.remove_product(product_name)


@when("I log out")
def log_out(nav_page):
    nav_page.logout()


# ─────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────

@then("I should remain on the products page")
def assert_remain_on_products(products_page):
    assert products_page.has_all_products_heading(), (
        "Expected the All Products heading — an empty search must NOT run a "
        "search and must leave the full catalogue shown"
    )


@then(parsers.re(r'the product results should contain "(?P<product_name>[^"]*)"'))
def assert_results_contain(products_page, product_name):
    assert products_page.has_product(product_name), (
        f"Expected {product_name!r} among the product results"
    )


@then("the search should return no product cards")
def assert_no_product_cards(products_page):
    count = products_page.get_result_count()
    assert count == 0, f"Expected zero product cards, found {count}"


@then(parsers.re(r'I should see the error message "(?P<expected_message>[^"]*)"'))
def assert_error_message(login_page, expected_message):
    actual = login_page.get_login_error()
    assert expected_message in actual, f"Expected {expected_message!r} in {actual!r}"


@then("I should not be logged in")
def assert_not_logged_in(nav_page):
    """Non-waiting probe — the waiting reader would time out rather than
    return False, so the assertion would never be reached."""
    assert not nav_page.is_logged_in(), "Unexpectedly logged in"


@then("I should remain on the login page")
def assert_remain_on_login(login_page):
    assert login_page.is_loaded(), "Expected to stay on the login page"


@then("I should be logged in")
def assert_logged_in(nav_page):
    assert nav_page.wait_until_logged_in(), "No session after logging in"


@then("I should see my account name in the navigation")
def assert_account_name_shown(nav_page):
    banner = nav_page.logged_in_name()
    assert "Logged in as" in banner, f"Expected a logged-in banner, got {banner!r}"


@then(parsers.re(r'I should see the product name "(?P<product_name>[^"]*)" on the detail page'))
def assert_detail_product_name(product_detail_page, product_name):
    actual = product_detail_page.product_name()
    assert actual == product_name, f"Expected detail name {product_name!r}, got {actual!r}"


@then(parsers.re(r'the cart should contain a row for "(?P<product_name>[^"]*)"'))
def assert_cart_contains(cart_page, product_name):
    assert cart_page.has_product(product_name), (
        f"Expected a cart row for {product_name!r}"
    )


@then(parsers.re(r'the cart should no longer contain a row for "(?P<product_name>[^"]*)"'))
def assert_cart_no_longer_contains(cart_page, product_name):
    assert cart_page.has_no_product(product_name), (
        f"Expected no cart row for {product_name!r} after removal"
    )
