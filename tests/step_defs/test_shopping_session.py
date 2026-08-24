"""Step definitions for features/shopping_session.feature.

Binds every Gherkin step to page-object methods only. No selectors here.
Real logins go through the `credentials` fixture; invalid data stays literal.
Presence is asserted with waiting readers, absence with non-waiting probes.
"""
from pytest_bdd import given, when, then, parsers, scenarios

from config.paths import feature_path

scenarios(str(feature_path("shopping_session")))


# ─────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────

@given("I am on the signup and login page")
@when("I am on the signup and login page")
def open_login_page(login_page, base_url):
    login_page.open_login_page(base_url)


@given("I am on the products page")
def open_products_page(products_page, base_url):
    products_page.open_listing(base_url)


# ─────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────

@when(parsers.re(r'I log in as a "(?P<role>[^"]*)" user'))
def login_as_role(login_page, credentials, role):
    email, password = credentials(role)
    login_page.login_as(email, password)


@when(parsers.re(r'I log in with email "(?P<email>[^"]*)" and password "(?P<password>[^"]*)"'))
def login_with_literal_credentials(login_page, email, password):
    login_page.login_as(email, password)


@when("I clear the credential fields")
def clear_credentials(login_page):
    login_page.clear_credentials()


@when(parsers.parse('I search for the product "{term}"'))
def search_for_product(products_page, term):
    products_page.search_for(term)


@when(parsers.parse('I open the product "{name}" from the search results'))
def open_product_from_search(products_page, name):
    products_page.open_product(name)


@when(parsers.parse('I open the product "{name}" from the listing'))
def open_product_from_listing(products_page, name):
    products_page.open_product(name)


@when("I add the product to the cart from the detail page")
def add_to_cart_from_detail(product_detail_page):
    product_detail_page.add_to_cart()


@when("I view the cart from the added-to-cart modal")
def view_cart_from_modal(product_detail_page):
    product_detail_page.view_cart_from_modal()


@when("I dismiss the added-to-cart modal")
def dismiss_added_modal(product_detail_page):
    product_detail_page.dismiss_added_modal()


@when("I view the cart")
def view_cart(cart_page, base_url):
    cart_page.open_cart(base_url)


@when(parsers.parse('I remove "{product_name}" from the cart'))
def remove_from_cart(cart_page, product_name):
    cart_page.remove_product(product_name)


@when("I log out")
def logout(nav_page):
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


@then(parsers.parse('the search results should include "{name}"'))
def assert_search_includes(products_page, name):
    assert products_page.has_result(name), f"Expected {name!r} in the search results"


@then("the search results should contain no products")
def assert_no_search_results(products_page):
    assert products_page.get_result_count() == 0, "Expected zero product cards"


@then(parsers.parse('I should see the product detail for "{name}"'))
def assert_product_detail(product_detail_page, name):
    actual = product_detail_page.product_name()
    assert name in actual, f"Expected product detail for {name!r}, got {actual!r}"


@then(parsers.parse('the cart should contain a row for "{product_name}"'))
def assert_cart_has_row(cart_page, product_name):
    assert cart_page.has_product_row(product_name), (
        f"Expected a cart row for {product_name!r}"
    )


@then(parsers.parse('the cart should no longer contain a row for "{product_name}"'))
def assert_cart_row_removed(cart_page, product_name):
    cart_page.wait_until_product_removed(product_name)


@then(parsers.re(r'I should see the error message "(?P<expected_message>[^"]*)"'))
def assert_error_message(login_page, expected_message):
    actual = login_page.get_login_error()
    assert expected_message in actual, f"Expected {expected_message!r} in {actual!r}"
