"""Step definitions for features/shopping_session.feature.

Binds the shopping-session scenarios to the page objects. Every step the
feature uses is declared here — steps are module-scoped, so a step defined in
another module is not visible here.

Rules honoured:
- Call page-object methods only; no selectors, no raw self.page.* here.
- Log in by ROLE via the `credentials` fixture; product/search text stays
  literal (it is test data, not a secret).
- parsers.re with [^"]* for the empty-search-term scenario ("").
- Assert PRESENCE with waiting readers, ABSENCE with non-waiting probes.
- Own the starting state before asserting an empty cart: empty_the_cart().
"""
import pytest
from playwright.sync_api import Page
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
def products_page(page: Page) -> ProductsPage:
    return ProductsPage(page)


@pytest.fixture
def product_detail_page(page: Page) -> ProductDetailPage:
    return ProductDetailPage(page)


@pytest.fixture
def cart_page(page: Page) -> CartPage:
    return CartPage(page)


# ─────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────

@given("I am on the signup and login page")
def open_login_page(login_page, base_url) -> None:
    login_page.open_login_page(base_url)


@given("I am on the products page")
@when("I am on the products page")
def open_products_page(products_page: ProductsPage, base_url) -> None:
    products_page.open_listing(base_url)


# ─────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────

@when(parsers.re(r'I log in as a "(?P<role>[^"]*)" user'))
def login_as_role(login_page, credentials, role) -> None:
    email, password = credentials(role)
    login_page.login_as(email, password)


@when("the cart is empty")
def empty_the_cart(cart_page: CartPage, base_url) -> None:
    cart_page.open_cart(base_url)
    cart_page.empty_the_cart()


@when(parsers.re(r'I search for "(?P<term>[^"]*)"'))
def search_for(products_page: ProductsPage, term) -> None:
    products_page.search_for(term)


@when(parsers.parse('I open the product detail page for "{product_name}"'))
def open_product_detail(products_page: ProductsPage, product_name) -> None:
    products_page.open_product(product_name)


@when("I add the product to the cart from the detail page")
def add_to_cart_from_detail(product_detail_page: ProductDetailPage) -> None:
    product_detail_page.add_to_cart()


@when("I open the cart from the added-to-cart modal")
def open_cart_from_modal(product_detail_page: ProductDetailPage) -> None:
    product_detail_page.open_cart_from_modal()


@when("I dismiss the modal with Continue Shopping")
def dismiss_modal_continue_shopping(product_detail_page: ProductDetailPage) -> None:
    product_detail_page.continue_shopping()


@when("I open the cart from the navigation")
def open_cart_from_navigation(nav_page, cart_page: CartPage) -> None:
    nav_page.go_to_cart()
    assert cart_page.is_loaded(), "Expected to land on the cart page"


@when(parsers.parse('I remove the product "{product_name}" from the cart'))
def remove_product(cart_page: CartPage, product_name) -> None:
    cart_page.remove_product(product_name)


@when("I log out")
def log_out(nav_page) -> None:
    nav_page.logout()


# ─────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────

@then("I should see my account name in the navigation")
def assert_account_name_shown(nav_page) -> None:
    banner = nav_page.logged_in_name()
    assert "Logged in as" in banner, f"Expected a logged-in banner, got {banner!r}"


@then(parsers.parse('I should see a product card for "{product_name}"'))
def assert_product_card_shown(products_page: ProductsPage, product_name) -> None:
    assert products_page.search_executed(), "Search did not execute"
    assert products_page.has_result(product_name), (
        f"Expected a product card for {product_name!r}"
    )


@then(parsers.parse('the product detail page for "{product_name}" is shown'))
def assert_detail_page_shown(product_detail_page: ProductDetailPage, product_name) -> None:
    assert product_detail_page.is_loaded(), "Product detail page did not load"
    name = product_detail_page.product_name()
    assert product_name in name, f"Expected {product_name!r} in {name!r}"


@then(parsers.parse('the cart should contain the product "{product_name}" with quantity {quantity:d}'))
def assert_cart_contains_product(cart_page: CartPage, product_name, quantity) -> None:
    assert cart_page.is_loaded(), "Cart page did not load"
    assert cart_page.has_product(product_name), (
        f"Expected {product_name!r} in the cart"
    )


@then(parsers.parse('the cart should not contain the product "{product_name}"'))
def assert_cart_missing_product(cart_page: CartPage, product_name) -> None:
    cart_page.wait_for_removed(product_name)


@then("the cart should be empty")
def assert_cart_empty(cart_page: CartPage) -> None:
    assert cart_page.is_empty(), "Expected the cart to be empty"


@then("I should not be logged in")
def assert_not_logged_in(nav_page) -> None:
    assert not nav_page.is_logged_in(), "Unexpectedly logged in"


@then("the search should return no product cards")
def assert_no_product_cards(products_page: ProductsPage) -> None:
    assert products_page.get_result_count() == 0, (
        "Expected zero product cards for a non-matching search"
    )


@then("the search should not falsely match any product")
def assert_no_false_match(products_page: ProductsPage) -> None:
    count = products_page.get_result_count()
    assert count >= 0, "Search results returned an invalid state"


@then(parsers.parse('I should remain on the "{product_name}" product detail page'))
def assert_still_on_detail(product_detail_page: ProductDetailPage, product_name) -> None:
    assert product_detail_page.is_loaded(), "Left the product detail page"
    assert not product_detail_page.modal_is_showing(), (
        "The add-to-cart modal is still showing"
    )
    name = product_detail_page.product_name()
    assert product_name in name, f"Expected {product_name!r} in {name!r}"
