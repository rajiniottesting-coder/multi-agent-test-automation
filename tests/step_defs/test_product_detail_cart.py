"""Step definitions for features/product_detail_cart.feature.

Binds the product-detail and cart Gherkin steps to the page objects generated
in this batch. Selectors live only in the page objects; these steps call named
methods and assert on their return values.
"""
from pytest_bdd import given, when, then, parsers, scenarios

from config.paths import feature_path

scenarios(str(feature_path("product_detail_cart")))


# ─────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────

@given("I am on the products page")
def open_products_page(products_page, base_url):
    products_page.open_products(base_url)


# ─────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────

@when(parsers.parse('I view the product "{product_name}"'))
def view_product(products_page, product_name):
    products_page.open_product_details(product_name)


@when(parsers.parse("I set the quantity to {quantity:d}"))
def set_quantity(product_detail_page, quantity):
    product_detail_page.set_quantity(quantity)


@when("I add the product to the cart")
def add_to_cart(product_detail_page):
    product_detail_page.add_to_cart()


@when("I click View Cart in the confirmation modal")
def click_view_cart_in_modal(product_detail_page):
    product_detail_page.view_cart()


@when("I click Continue Shopping in the confirmation modal")
def click_continue_shopping_in_modal(product_detail_page):
    product_detail_page.continue_shopping()


@when("I go to the cart via the navigation")
def go_to_cart_via_nav(nav_page):
    nav_page.go_to_cart()


# ─────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────

@then(parsers.parse('the product detail page should show the name "{expected_name}"'))
def assert_product_name(product_detail_page, expected_name):
    actual = product_detail_page.product_name()
    assert expected_name in actual, f"Expected name {expected_name!r} in {actual!r}"


@then(parsers.parse('the product detail page should show the price "{expected_price}"'))
def assert_product_price(product_detail_page, expected_price):
    actual = product_detail_page.product_price()
    assert expected_price in actual, f"Expected price {expected_price!r} in {actual!r}"


@then("the product detail page should show the availability label")
def assert_availability_label(product_detail_page):
    assert product_detail_page.has_availability_label(), "Expected the Availability label"


@then("the product detail page should show the condition label")
def assert_condition_label(product_detail_page):
    assert product_detail_page.has_condition_label(), "Expected the Condition label"


@then("the product detail page should show the brand label")
def assert_brand_label(product_detail_page):
    assert product_detail_page.has_brand_label(), "Expected the Brand label"


@then(parsers.parse('the cart should contain "{product_name}" with quantity {quantity:d}'))
def assert_cart_contains(cart_page, product_name, quantity):
    cart_page.wait_for_product(product_name, present=True)
    actual = cart_page.quantity_for(product_name)
    assert actual == quantity, (
        f"Expected quantity {quantity} for {product_name!r}, got {actual}"
    )


@then(parsers.parse('I should remain on the "{product_name}" product detail page'))
def assert_remain_on_detail(product_detail_page, product_name):
    assert product_detail_page.is_loaded(), "Expected to stay on the product detail page"
    actual = product_detail_page.product_name()
    assert product_name in actual, (
        f"Expected to remain on {product_name!r} detail page, name was {actual!r}"
    )
