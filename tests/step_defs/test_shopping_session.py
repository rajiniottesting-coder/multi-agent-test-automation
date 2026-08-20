"""Step definitions for features/shopping_session.feature.

Binds the shopping-session scenarios to page-object methods for login,
product search, cart management, and logout.

Conventions (see tests/step_defs/test_login.py):
- Every step the feature uses is declared here — steps are module-scoped.
- Step definitions call page-object methods only; no selectors here.
- Real logins go through the `credentials` fixture resolved by ROLE.
- Invalid/empty credentials stay literal — they are test data, not secrets.
- parsers.re with [^"]* wherever a quoted value could be empty.
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
# When — login
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
    """Literal values, for invalid and empty-field scenarios."""
    login_page.login_as(email, password)


@when("I clear the credential fields")
def clear_credentials(login_page):
    login_page.clear_credentials()


@when("I log out")
def logout(nav_page):
    nav_page.logout()


# ─────────────────────────────────────────────────────────────
# When — products & search
# ─────────────────────────────────────────────────────────────

@when("I open the products listing")
def open_products_listing(nav_page):
    nav_page.open_products()


@when(parsers.re(r'I search for "(?P<term>[^"]*)"'))
def search_for_term(products_page, term):
    products_page.search_for(term)


@when(parsers.re(r'I view the product "(?P<product_name>[^"]*)" from the results'))
def view_product_from_results(products_page, product_name):
    products_page.view_product(product_name)


# ─────────────────────────────────────────────────────────────
# When — product detail & cart
# ─────────────────────────────────────────────────────────────

@when("I add the product to the cart")
def add_product_to_cart(product_detail_page):
    product_detail_page.add_product_to_cart()


@when("I view the cart from the product modal")
def view_cart_from_modal(product_detail_page):
    product_detail_page.view_cart_from_modal()


@when(parsers.re(r'I remove "(?P<product_name>[^"]*)" from the cart'))
def remove_product_from_cart(cart_page, product_name):
    cart_page.remove_product(product_name)


# ─────────────────────────────────────────────────────────────
# Then — session
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


@then("I should remain on the login page")
def assert_still_on_login(login_page):
    assert login_page.is_loaded(), "Expected to stay on the login page"


@then(parsers.re(r'I should see the error message "(?P<expected_message>[^"]*)"'))
def assert_error_message(login_page, expected_message):
    actual = login_page.get_login_error()
    assert expected_message in actual, f"Expected {expected_message!r} in {actual!r}"


# ─────────────────────────────────────────────────────────────
# Then — search results
# ─────────────────────────────────────────────────────────────

@then("the search results should be displayed")
def assert_search_results_displayed(products_page):
    assert products_page.search_executed(), "Search did not execute"


@then(parsers.re(r'I should see "(?P<product_name>[^"]*)" in the search results'))
def assert_product_in_results(products_page, product_name):
    assert products_page.has_product(product_name), (
        f"Expected {product_name!r} among the search results, "
        f"got {products_page.get_result_names()!r}"
    )


@then("no product cards should be shown")
def assert_no_product_cards(products_page):
    count = products_page.get_result_count()
    assert count == 0, f"Expected no product cards, found {count}"


@then(parsers.re(r'I should be on the product detail page for "(?P<product_name>[^"]*)"'))
def assert_on_product_detail(product_detail_page, product_name):
    assert product_detail_page.is_loaded(), "Product detail page did not load"
    actual = product_detail_page.product_name()
    assert product_name in actual, f"Expected {product_name!r} in {actual!r}"


# ─────────────────────────────────────────────────────────────
# Then — cart
# ─────────────────────────────────────────────────────────────

@then(parsers.re(r'the cart should contain "(?P<product_name>[^"]*)"'))
def assert_cart_contains(cart_page, product_name):
    assert cart_page.is_loaded(), "Cart page did not load"
    assert cart_page.has_product(product_name), (
        f"Expected {product_name!r} in the cart, "
        f"got {cart_page.get_product_names()!r}"
    )


@then("the cart should be empty")
def assert_cart_empty(cart_page):
    assert cart_page.is_empty(), "Expected the cart to be empty"
