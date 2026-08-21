"""Step definitions for features/shopping_session.feature.

Mirrors the conventions of the reserved login step-def file:
  - every step the feature uses is declared here (steps are module-scoped)
  - step defs call page-object methods only; no selectors, no raw page.* calls
  - real logins go through a ROLE via the `credentials` fixture; invalid data
    (empty values, wrong or literal passwords) stays literal — it is test data
  - PRESENCE is asserted with a waiting reader, ABSENCE with a non-waiting probe
"""
import pytest
from pytest_bdd import given, when, then, parsers, scenarios

from config.paths import feature_path
from pages.products_page import ProductsPage
from pages.product_detail_page import ProductDetailPage
from pages.cart_page import CartPage

scenarios(str(feature_path("shopping_session")))


# ─────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────

@pytest.fixture
def products_page(page) -> ProductsPage:
    return ProductsPage(page)


@pytest.fixture
def product_detail_page(page) -> ProductDetailPage:
    return ProductDetailPage(page)


@pytest.fixture
def cart_page(page) -> CartPage:
    return CartPage(page)


# ─────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────

@given("I am on the signup and login page")
def open_login_page(login_page, base_url) -> None:
    login_page.open(base_url)


# ─────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────

@when(parsers.re(r'I log in as a "(?P<role>[^"]*)" user$'))
def login_as_role(login_page, credentials, role) -> None:
    email, password = credentials(role)
    login_page.login_as(email, password)


@when(parsers.re(r'I log in as a "(?P<role>[^"]*)" user with an incorrect password'))
def login_as_role_wrong_password(login_page, credentials, role) -> None:
    email, _ = credentials(role)
    login_page.login_as(email, "WrongPass!123")


@when(parsers.re(r'I log in with email "(?P<email>[^"]*)" and password "(?P<password>[^"]*)"'))
def login_with_literal_credentials(login_page, email, password) -> None:
    login_page.login_as(email, password)


@when("I clear the credential fields")
def clear_credentials(login_page) -> None:
    login_page.clear_credentials()


@when("I go to the products page")
def go_to_products(products_page, base_url) -> None:
    products_page.open_listing(base_url)


@when(parsers.parse('I search for "{term}"'))
def search_for_term(products_page, term) -> None:
    products_page.search_for(term)


@when(parsers.parse('I view the product "{product_name}"'))
def view_product(products_page, product_name) -> None:
    products_page.open_product(product_name)


@when("I add the product to the cart")
def add_product_to_cart(product_detail_page) -> None:
    product_detail_page.add_to_cart()


@when("I go to the cart from the added-to-cart modal")
def go_to_cart_from_modal(product_detail_page) -> None:
    product_detail_page.view_cart_from_modal()


@when(parsers.parse('I remove the product "{product_name}" from the cart'))
def remove_product_from_cart(cart_page, product_name) -> None:
    cart_page.remove_product(product_name)


@when("I log out")
def log_out(nav_page) -> None:
    nav_page.logout()


# ─────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────

@then("I should be logged in")
def assert_logged_in(nav_page) -> None:
    assert nav_page.wait_until_logged_in(), "No session after logging in"


@then("I should not be logged in")
def assert_not_logged_in(nav_page) -> None:
    assert not nav_page.is_logged_in(), "Unexpectedly logged in"


@then("I should see my account name in the navigation")
def assert_account_name_shown(nav_page) -> None:
    banner = nav_page.logged_in_name()
    assert "Logged in as" in banner, f"Expected a logged-in banner, got {banner!r}"


@then("the search should have executed")
def assert_search_executed(products_page) -> None:
    assert products_page.search_executed(), "Search does not appear to have executed"


@then(parsers.parse('I should see the product "{product_name}" in the results'))
def assert_product_in_results(products_page, product_name) -> None:
    assert products_page.has_product(product_name), \
        f"Expected product {product_name!r} in the search results"


@then(parsers.parse('I should be on the product detail page for "{product_name}"'))
def assert_on_product_detail(product_detail_page, product_name) -> None:
    assert product_detail_page.is_loaded(), "Product detail page did not load"
    actual = product_detail_page.product_name()
    assert product_name in actual, f"Expected {product_name!r} in {actual!r}"


@then(parsers.parse('the cart should contain the product "{product_name}"'))
def assert_cart_contains(cart_page, product_name) -> None:
    assert cart_page.has_product(product_name), \
        f"Expected the cart to contain {product_name!r}"


@then("the cart should be empty")
def assert_cart_empty(cart_page) -> None:
    assert cart_page.is_empty(), "Expected the cart to be empty"


@then("I should remain on the login page")
def assert_still_on_login(login_page) -> None:
    assert login_page.is_loaded(), "Expected to stay on the login page"


@then(parsers.re(r'I should see the error message "(?P<expected_message>[^"]*)"'))
def assert_error_message(login_page, expected_message) -> None:
    actual = login_page.get_login_error()
    assert expected_message in actual, f"Expected {expected_message!r} in {actual!r}"


@then("I should see no product results")
def assert_no_product_results(products_page) -> None:
    assert products_page.get_result_card_count() == 0, \
        "Expected no product result cards"


@then("I should see the login or signup link in the navigation")
def assert_login_signup_link(nav_page) -> None:
    assert nav_page.is_visible(nav_page.sel("signup_login_link")), \
        "Expected the Login/Signup link to be present in the navigation"
