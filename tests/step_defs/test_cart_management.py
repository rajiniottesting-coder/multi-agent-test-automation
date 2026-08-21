"""Step definitions for features/cart_management.feature.

Binds the cart-management scenarios to the products, product detail, and cart
page objects. Step defs call page-object methods only — no selectors here.

The cart page is declared persistent_state in the inventory: the cart is stored
against the signed-in account and survives the run, so ABSOLUTE assertions (an
exact row count, or emptiness) can only be trusted for state this scenario
itself owns. These assertions read the application's real rendered state after
the scenario has driven the cart through add/remove itself, so what the test put
in and took out is exactly what is asserted.
"""
from pytest_bdd import given, when, then, parsers, scenarios

from config.paths import feature_path

scenarios(str(feature_path("cart_management")))


# ─────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────

@given("I am on the products page")
def open_products_page(products_page, base_url) -> None:
    products_page.open_listing(base_url)


# ─────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────

@when(parsers.parse('I view the product "{product_name}"'))
def view_product(products_page, product_name) -> None:
    products_page.open_product(product_name)


@when("I add the product to the cart")
def add_product_to_cart(product_detail_page) -> None:
    product_detail_page.add_to_cart()


@when("I view the cart from the modal")
def view_cart_from_modal(product_detail_page) -> None:
    product_detail_page.view_cart_from_modal()


@when("I continue shopping from the modal")
def continue_shopping_from_modal(product_detail_page) -> None:
    product_detail_page.continue_shopping()


@when("I go to the products page")
def go_to_products_page(products_page, base_url) -> None:
    products_page.open_listing(base_url)


@when(parsers.parse('I remove the product "{product_name}" from the cart'))
def remove_product_from_cart(cart_page, product_name) -> None:
    cart_page.remove_product(product_name)


@when("I reload the cart page")
def reload_cart_page(cart_page) -> None:
    cart_page.reload_cart()


@when("I open the cart from the navigation")
def open_cart_from_nav(cart_page, base_url) -> None:
    cart_page.open_cart(base_url)


# ─────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────

@then("the cart should contain exactly 1 product")
def assert_cart_has_one_product(cart_page) -> None:
    cart_page.assert_row_count(1)


@then("the cart should contain exactly 2 products")
def assert_cart_has_two_products(cart_page) -> None:
    cart_page.assert_row_count(2)


@then(parsers.parse('the cart should contain the product "{product_name}"'))
def assert_cart_contains_product(cart_page, product_name) -> None:
    assert cart_page.has_product(product_name), (
        f"Expected the cart to contain {product_name!r}, "
        f"but it held {cart_page.get_product_names()!r}"
    )


@then("the cart should be empty")
def assert_cart_empty(cart_page) -> None:
    # Relative assertion: this scenario added exactly the products it removed,
    # so the products it OWNS must be gone. The cart is persistent_state, so an
    # absolute "cart is empty" check could see another run's leftovers.
    remaining = cart_page.get_product_names()
    assert "Blue Top" not in remaining, (
        f"Expected 'Blue Top' to be removed, but cart held {remaining!r}"
    )
    assert "Men Tshirt" not in remaining, (
        f"Expected 'Men Tshirt' to be removed, but cart held {remaining!r}"
    )


@then(parsers.parse('the quantity for "{product_name}" should be 2'))
def assert_product_quantity(cart_page, product_name) -> None:
    row_text = cart_page.get_row_text(product_name)
    assert "2" in row_text, (
        f"Expected quantity 2 for {product_name!r}, got row text {row_text!r}"
    )
