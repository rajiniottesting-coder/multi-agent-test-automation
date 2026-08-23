"""Step definitions for features/shopping_session.feature.

Binds every Gherkin step in shopping_session.feature to page-object calls.
Selectors live in the page objects only; step definitions call named methods.
Real credentials are resolved by ROLE through the `credentials` fixture;
invalid data (wrong passwords, unknown emails, empty fields) stays literal.
Presence is asserted with waiting readers, absence with non-waiting probes.
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
    products_page.open_products(base_url)


# ─────────────────────────────────────────────────────────────
# When — authentication
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


@when("I empty the cart")
def empty_the_cart(cart_page, base_url):
    cart_page.open_cart(base_url)
    cart_page.empty_the_cart()


# ─────────────────────────────────────────────────────────────
# When — browsing and searching
# ─────────────────────────────────────────────────────────────

@when("I open the products page")
def when_open_products(products_page, base_url):
    products_page.open_products(base_url)


@when(parsers.re(r'I search for "(?P<term>[^"]*)"'))
def search_for(products_page, term):
    products_page.search_for(term)


@when(parsers.parse('I open the product detail for "{product_name}"'))
def open_product_detail(products_page, product_name):
    products_page.open_product_detail(product_name)


@when("I add the product to the cart")
def add_product_to_cart(product_detail_page):
    product_detail_page.add_product_to_cart()


@when("I view the cart from the modal")
def view_cart_from_modal(product_detail_page):
    product_detail_page.view_cart_from_modal()


@when("I continue shopping from the modal")
def continue_shopping_from_modal(product_detail_page):
    product_detail_page.continue_shopping()


@when("I open the cart from the navigation")
def open_cart_from_nav(nav_page):
    nav_page.go_to_cart()


@when(parsers.parse('I remove "{product_name}" from the cart'))
def remove_from_cart(cart_page, product_name):
    cart_page.remove_product(product_name)


# ─────────────────────────────────────────────────────────────
# Then — authentication state
# ─────────────────────────────────────────────────────────────

@then("I should be logged in")
def assert_logged_in(nav_page):
    assert nav_page.wait_until_logged_in(), "No session after logging in"


@then("I should not be logged in")
def assert_not_logged_in(nav_page):
    """Non-waiting probe: the waiting reader would time out on absence."""
    assert not nav_page.is_logged_in(), "Unexpectedly logged in"


@then("I should see my account name in the navigation")
def assert_account_name_shown(nav_page):
    banner = nav_page.logged_in_name()
    assert "Logged in as" in banner, f"Expected a logged-in banner, got {banner!r}"


@then("I should see the login and signup link")
def assert_login_signup_link_shown(nav_page):
    assert nav_page.wait_until_logged_in() is False or not nav_page.is_logged_in(), \
        "Expected the Signup / Login link (not logged in)"


@then(parsers.re(r'I should see the error message "(?P<expected_message>[^"]*)"'))
def assert_error_message(login_page, expected_message):
    actual = login_page.get_login_error()
    assert expected_message in actual, f"Expected {expected_message!r} in {actual!r}"


@then("I should remain on the login page")
def assert_still_on_login(login_page):
    assert login_page.is_loaded(), "Expected to stay on the login page"


# ─────────────────────────────────────────────────────────────
# Then — search results
# ─────────────────────────────────────────────────────────────

@then("I should see the search results")
def assert_search_results_shown(products_page):
    assert products_page.has_searched(), "Search does not appear to have executed"


@then(parsers.parse('the search results should contain "{product_name}"'))
def assert_results_contain(products_page, product_name):
    assert products_page.has_searched(), "Search does not appear to have executed"
    assert products_page.has_product(product_name), \
        f"Expected {product_name!r} in the search results"


@then("the search should return no product cards")
def assert_no_product_cards(products_page):
    assert products_page.has_searched(), "Search does not appear to have executed"
    assert products_page.get_result_count() == 0, \
        "Expected zero product cards for a non-matching search"


@then(parsers.parse('the search should not falsely match "{product_name}"'))
def assert_no_false_match(products_page, product_name):
    assert not products_page.has_product(product_name), \
        f"Search falsely matched {product_name!r}"


# ─────────────────────────────────────────────────────────────
# Then — product detail
# ─────────────────────────────────────────────────────────────

@then(parsers.parse('the product detail page for "{product_name}" is shown'))
def assert_product_detail_shown(product_detail_page, product_name):
    assert product_detail_page.is_loaded(), "Product detail page did not load"
    actual = product_detail_page.product_name()
    assert product_name in actual, \
        f"Expected product detail for {product_name!r}, got {actual!r}"


# ─────────────────────────────────────────────────────────────
# Then — cart contents
# ─────────────────────────────────────────────────────────────

@then(parsers.parse('the cart should contain "{product_name}" with quantity {quantity:d}'))
def assert_cart_contains_with_quantity(cart_page, product_name, quantity):
    assert cart_page.has_product(product_name), \
        f"Expected {product_name!r} in the cart"
    actual = cart_page.get_quantity(product_name)
    assert actual == quantity, \
        f"Expected quantity {quantity} for {product_name!r}, got {actual}"


@then(parsers.parse('the cart should not contain "{product_name}"'))
def assert_cart_not_contains(cart_page, product_name):
    cart_page.wait_until_product_removed(product_name)


@then("the cart should be empty")
def assert_cart_empty(cart_page):
    assert cart_page.is_empty(), "Expected the cart to be empty"
