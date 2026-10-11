"""Step definitions for features/cart_add_remove.feature.

Binds the cart add/remove scenarios to page-object methods, following the
login reference style:
  - every step the feature uses is declared here (steps are module-scoped)
  - page-object methods only; no selectors in this file
  - PRESENCE is asserted with waiting readers, ABSENCE with non-waiting probes
  - the anonymous cart belongs to this session, so quantities added by the
    test are asserted relatively (the row this test touched), which holds
    whatever the session started with
"""
import pytest
from pytest_bdd import given, when, then, parsers, scenarios

from config.paths import feature_path
from pages.products_page import ProductsPage
from pages.product_detail_page import ProductDetailPage
from pages.cart_page import CartPage

scenarios(str(feature_path("cart_add_remove")))


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
# Given / When — products listing
# ─────────────────────────────────────────────────────────────

@given("I am on the products listing page")
@when("I am on the products listing page")
def open_products_listing(products_page, base_url) -> None:
    products_page.open_products(base_url)


@when(parsers.parse('I open the product details page for "{product_name}"'))
def open_product_details(product_detail_page, product_name) -> None:
    product_detail_page.open_product(product_name)


# ─────────────────────────────────────────────────────────────
# When — cart actions
# ─────────────────────────────────────────────────────────────

@when("I add the product to the cart")
def add_product_to_cart(product_detail_page) -> None:
    product_detail_page.add_to_cart()


@when("I view the cart from the modal")
def view_cart_from_modal(product_detail_page) -> None:
    product_detail_page.view_cart_from_modal()


@when("I continue shopping from the modal")
def continue_shopping_from_modal(product_detail_page) -> None:
    product_detail_page.continue_shopping()


@when(parsers.parse('I remove "{product_name}" from the cart'))
def remove_product_from_cart(cart_page, product_name) -> None:
    cart_page.remove_product(product_name)


# ─────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────

@then(parsers.parse('the cart should contain "{product_name}" with quantity {quantity:d}'))
def assert_cart_contains_with_quantity(cart_page, product_name, quantity) -> None:
    cart_page.wait_until_contains(product_name)
    actual = cart_page.quantity_for(product_name)
    assert actual == quantity, (
        f"Expected {product_name!r} with quantity {quantity}, got {actual}"
    )


@then(parsers.parse('the cart should not contain "{product_name}"'))
def assert_cart_does_not_contain(cart_page, product_name) -> None:
    cart_page.wait_until_not_contains(product_name)
