"""Step definitions for features/shopping_session.feature.

Binds the shopping-session scenarios to page-object methods. Every step the
feature file uses is declared here — pytest-bdd steps are module-scoped, so a
step defined elsewhere is not visible to this module.

Conventions (see tests/step_defs/test_login.py):
  - Call page-object methods only; never a selector in a step definition.
  - Log in by ROLE via the `credentials` fixture. Invalid/literal data stays
    literal — it is test data, not a secret.
  - parsers.re with [^"]* wherever a quoted value could be empty.
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
    login_page.open(base_url)


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
    login_page.login_as(email, "WrongPass!123")


@when(parsers.re(r'I log in with email "(?P<email>[^"]*)" and password "(?P<password>[^"]*)"'))
def login_with_literal_credentials(login_page, email, password):
    """Literal values, for unknown-email and empty-field scenarios."""
    login_page.login_as(email, password)


@when("I clear the credential fields")
def clear_credentials(login_page):
    login_page.clear_credentials()


@when("I open the products page")
def open_products(nav_page):
    nav_page.open_products()


@when(parsers.parse('I search for "{term}"'))
def search_for(products_page, term):
    products_page.search_for(term)


@when(parsers.parse('I open the product "{product_name}" from the results'))
def open_product(products_page, product_name):
    products_page.open_product(product_name)


@when("I add the product to the cart")
def add_product_to_cart(product_detail_page):
    product_detail_page.add_product_to_cart()


@when("I view the cart from the modal")
def view_cart_from_modal(product_detail_page):
    product_detail_page.view_cart_from_modal()


@when(parsers.parse('I remove the product "{product_name}" from the cart'))
def remove_product(cart_page, product_name):
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


@then("I should see the login link in the navigation")
def assert_login_link_shown(nav_page):
    assert nav_page.wait_until_logged_out(), "Expected the Login/Signup link to be present"


@then("the search results should be shown")
def assert_search_results_shown(products_page):
    assert products_page.search_executed(), "Search did not appear to execute"


@then(parsers.parse('I should see the product "{product_name}" priced "{price}" in the results'))
def assert_product_in_results(products_page, product_name, price):
    names = products_page.get_product_names()
    assert products_page.has_product(product_name), (
        f"Expected {product_name!r} in results, got {names!r}"
    )


@then(parsers.parse('I should be on the product detail page for "{product_name}"'))
def assert_on_product_detail(product_detail_page, product_name):
    assert product_detail_page.is_loaded(), "Product detail page did not load"
    actual = product_detail_page.product_name()
    assert product_name in actual, f"Expected {product_name!r} on detail page, got {actual!r}"


@then(parsers.parse('the cart should contain the product "{product_name}" priced "{price}"'))
def assert_cart_contains(cart_page, product_name, price):
    assert cart_page.is_loaded(), "Cart page did not load"
    names = cart_page.get_product_names()
    assert cart_page.has_product(product_name), (
        f"Expected {product_name!r} in cart, got {names!r}"
    )


@then("the cart should be empty")
def assert_cart_empty(cart_page):
    assert cart_page.is_empty(), "Expected the cart to be empty"


@then(parsers.re(r'I should see the error message "(?P<expected_message>[^"]*)"'))
def assert_error_message(login_page, expected_message):
    actual = login_page.get_login_error()
    assert expected_message in actual, f"Expected {expected_message!r} in {actual!r}"


@then("no product results should be displayed")
def assert_no_product_results(products_page):
    count = products_page.get_result_card_count()
    assert count == 0, f"Expected no product cards, found {count}"
