"""Step definitions for features/shopping_session.feature.

Binds the shopping-session feature to the login, nav, products, product
detail, and cart page objects. Every step the feature uses is declared here,
since pytest-bdd steps are module-scoped.

Conventions (see reference test_login.py):
  - Call page-object methods only; never a selector in a step definition.
  - Log in by ROLE via the `credentials` fixture. Invalid/empty data stays
    literal — it is test data, not a secret.
  - Use parsers.re with [^"]* where a quoted value can be empty.
  - Assert PRESENCE with a waiting reader, ABSENCE with a non-waiting probe.
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
    login_page.login_as(email, "definitely-not-the-password")


@when(parsers.re(r'I log in with email "(?P<email>[^"]*)" and password "(?P<password>[^"]*)"'))
def login_with_literal_credentials(login_page, email, password):
    """Literal values, for malformed-email and empty-field scenarios."""
    login_page.login_as(email, password)


@when("I clear the credential fields")
def clear_credentials(login_page):
    login_page.clear_credentials()


@when("I go to the products page")
def go_to_products_page(nav_page):
    nav_page.go_to_products()


@when(parsers.parse('I search for "{term}"'))
def search_for(products_page, term):
    products_page.search_for(term)


@when(parsers.parse('I open the product "{name}" from the search results'))
def open_product_from_results(products_page, name):
    products_page.open_product(name)


@when("I add the product to the cart")
def add_product_to_cart(product_detail_page):
    product_detail_page.add_product_to_cart()


@when("I view the cart from the confirmation")
def view_cart_from_confirmation(product_detail_page):
    product_detail_page.view_cart_from_confirmation()


@when(parsers.parse('I remove "{name}" from the cart'))
def remove_from_cart(cart_page, name):
    cart_page.remove_product(name)


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


@then(parsers.parse('the search results should include "{name}"'))
def assert_search_includes(products_page, name):
    assert products_page.has_run_search(), "Search did not execute"
    names = products_page.get_result_names()
    assert any(name in n for n in names), f"Expected {name!r} in results {names!r}"


@then("the search should return no product cards")
def assert_no_result_cards(products_page):
    assert products_page.has_run_search(), "Search did not execute"
    assert products_page.get_result_count() == 0, (
        f"Expected zero product cards, got {products_page.get_result_count()}"
    )


@then(parsers.parse('the product detail page should show "{name}"'))
def assert_detail_shows(product_detail_page, name):
    assert product_detail_page.is_loaded(), "Product detail page did not load"
    actual = product_detail_page.product_name()
    assert name in actual, f"Expected {name!r} in detail name {actual!r}"


@then("I should see the added to cart confirmation")
def assert_added_confirmation(product_detail_page):
    assert product_detail_page.has_added_confirmation(), (
        "Expected the add-to-cart confirmation modal"
    )


@then(parsers.parse('the cart should contain a row for "{name}"'))
def assert_cart_contains_row(cart_page, name):
    assert cart_page.is_loaded(), "Cart page did not load"
    cart_page.wait_for_product_row(name)


@then(parsers.parse('the cart should not contain a row for "{name}"'))
def assert_cart_missing_row(cart_page, name):
    """Waiting call for absence — re-checks until the row is gone."""
    cart_page.wait_for_product_row_gone(name)


@then(parsers.re(r'I should see the error message "(?P<expected_message>[^"]*)"'))
def assert_error_message(login_page, expected_message):
    actual = login_page.get_login_error()
    assert expected_message in actual, f"Expected {expected_message!r} in {actual!r}"
