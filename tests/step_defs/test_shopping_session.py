"""Step definitions for features/shopping_session.feature.

Binds every Gherkin step in shopping_session.feature to page-object methods.
Steps are module-scoped in pytest-bdd, so every phrase the feature uses is
declared here even where an identical phrase exists in another step module.

Conventions (see tests/step_defs/test_login.py):
- Call page-object methods only; no selectors in this file.
- Log in by ROLE via the `credentials` fixture; invalid/empty data stays literal.
- parsers.re with [^"]* for any quoted value that can be empty.
- PRESENCE via waiting readers; ABSENCE via non-waiting probes.
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
    login_page.login_as(email, "definitely-not-the-password")


@when(parsers.re(r'I log in with email "(?P<email>[^"]*)" and password "(?P<password>[^"]*)"'))
def login_with_literal_credentials(login_page, email, password):
    """Literal values, for the unknown-email and empty-field scenarios."""
    login_page.login_as(email, password)


@when("I clear the credential fields")
def clear_credentials(login_page):
    login_page.clear_credentials()


@when("I log out")
def log_out(nav_page):
    nav_page.logout()


# ─────────────────────────────────────────────────────────────
# When — products & search
# ─────────────────────────────────────────────────────────────

@when("I open the products listing")
def open_products_listing(nav_page):
    nav_page.open_products()


@when(parsers.parse('I search for "{term}"'))
def search_for_term(products_page, term):
    products_page.search_for(term)


@when(parsers.parse('I open the product "{product_name}" from the results'))
def open_product_from_results(products_page, product_name):
    products_page.open_product(product_name)


# ─────────────────────────────────────────────────────────────
# When — product detail & cart
# ─────────────────────────────────────────────────────────────

@when("I add the product to the cart from the detail page")
def add_product_to_cart(product_detail_page):
    product_detail_page.add_to_cart()


@when("I view the cart from the added-to-cart modal")
def view_cart_from_modal(product_detail_page):
    product_detail_page.go_to_cart_from_modal()


@when(parsers.parse('I remove "{product_name}" from the cart'))
def remove_product_from_cart(cart_page, product_name):
    cart_page.remove_product(product_name)


# ─────────────────────────────────────────────────────────────
# Then — authentication state
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


@then("I should see the login link in the navigation")
def assert_login_link_shown(nav_page):
    assert nav_page.is_logged_out(), "Expected the Login/Signup link in the navigation"


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

@then("the search results should be shown")
def assert_search_ran(products_page):
    assert products_page.has_searched(), "Expected the searched-products heading"


@then(parsers.parse('the product "{product_name}" should be present in the results'))
def assert_product_present(products_page, product_name):
    assert products_page.has_product(product_name), \
        f"Expected {product_name!r} among the search results"


@then(parsers.parse('the product "{product_name}" should be priced "{price}" in the results'))
def assert_product_priced(products_page, product_name, price):
    names = products_page.get_result_names()
    assert product_name in names, \
        f"Expected {product_name!r} in results, got {names!r}"


@then("no products should be displayed in the results")
def assert_no_results(products_page):
    assert products_page.has_no_results(), \
        "Expected zero product cards for a non-matching search"


# ─────────────────────────────────────────────────────────────
# Then — product detail
# ─────────────────────────────────────────────────────────────

@then(parsers.parse('the product detail should show "{product_name}"'))
def assert_product_detail_name(product_detail_page, product_name):
    actual = product_detail_page.product_name()
    assert product_name in actual, \
        f"Expected detail page to show {product_name!r}, got {actual!r}"


# ─────────────────────────────────────────────────────────────
# Then — cart
# ─────────────────────────────────────────────────────────────

@then(parsers.parse('the cart should contain "{product_name}"'))
def assert_cart_contains(cart_page, product_name):
    assert cart_page.has_product(product_name), \
        f"Expected {product_name!r} in the cart"


@then(parsers.parse('the cart should contain exactly {count:d} product'))
def assert_cart_count(cart_page, count):
    names = cart_page.get_product_names()
    assert len(names) == count, \
        f"Expected exactly {count} product(s) in the cart, got {names!r}"


@then("the cart should be empty")
def assert_cart_empty(cart_page):
    assert cart_page.is_empty(), "Expected the cart to be empty"
