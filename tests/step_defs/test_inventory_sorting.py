"""
Step definitions for features/inventory_sorting.feature.
Each @given/@when/@then maps an English line to a Python action.
"""
import pytest
from pytest_bdd import scenarios, given, when, then, parsers

from pages.login_page import LoginPage
from pages.inventory_page import InventoryPage
from pages.product_detail_page import ProductDetailPage
from pathlib import Path
from config.paths import feature_path


# Bind this test module to the feature file
scenarios(str(feature_path("inventory_sorting")))


# === Page Object fixtures (created per-test) ===

@pytest.fixture
def login_page(page):
    return LoginPage(page)


@pytest.fixture
def inventory_page(page):
    return InventoryPage(page)


@pytest.fixture
def product_detail_page(page):
    return ProductDetailPage(page)


# === GIVEN steps ===

@given("I am on the SauceDemo login page")
def open_login_page(login_page, base_url):
    login_page.open(base_url)


@given("I have added at least one item to the cart")
def add_item_to_cart_given(inventory_page):
    # This step is used to ensure a cart badge is present for persistence tests.
    # The actual adding is done in a WHEN step.
    inventory_page.add_first_item_to_cart()


@given(parsers.parse('The inventory page is sorted by "{sort_order}"'))
def verify_inventory_sorted_initially(inventory_page, sort_order):
    # This step assumes the user is already on the inventory page and logged in.
    # We need to ensure the sorting is applied before proceeding.
    # If the sort_order is the default, we don't need to do anything.
    # Otherwise, we apply the sort.
    if sort_order != "Name (A to Z)":
        inventory_page.select_sort_option(sort_order)
    # We also need to capture the current state of the products to compare later.
    # This is implicitly handled by the page object's methods that return sorted lists.


@given("the inventory items are sorted by name ascending")
def given_sorted_by_name_asc(inventory_page):
    inventory_page.select_sort_option("Name (A to Z)")


@given("the inventory items are sorted by name descending")
def given_sorted_by_name_desc(inventory_page):
    inventory_page.select_sort_option("Name (Z to A)")


@given("the inventory items are sorted by price ascending")
def given_sorted_by_price_asc(inventory_page):
    inventory_page.select_sort_option("Price (low to high)")


@given("the inventory items are sorted by price descending")
def given_sorted_by_price_desc(inventory_page):
    inventory_page.select_sort_option("Price (high to low)")


# === WHEN steps ===

@when(parsers.parse('I log in with username "{username}" and password "{password}"'))
def login_with_credentials(login_page, username, password):
    login_page.login_as(username, password)


@when("I refresh the inventory page")
def refresh_inventory_page(inventory_page):
    inventory_page.page.reload()


@when("I add at least one item to the cart")
def add_item_to_cart_when(inventory_page):
    inventory_page.add_first_item_to_cart()


@when("I navigate to the cart page")
def navigate_to_cart(inventory_page):
    inventory_page.go_to_cart()


@when("I navigate back to the inventory page")
def navigate_back_to_inventory(cart_page):
    # Assuming cart_page has a 'continue_shopping' method or similar
    # If not, this might need to be handled by inventory_page or a base page method
    cart_page.click_continue_shopping()


@when(parsers.parse('I select the sort option "{sort_option}"'))
def select_sort_option(inventory_page, sort_option):
    inventory_page.select_sort_option(sort_option)


@when("I click on the first product name")
def click_first_product_name(inventory_page):
    inventory_page.click_first_product_link()


@when("I click the 'Back to products' button")
def back_to_products(product_detail_page):
    product_detail_page.go_back_to_inventory()


# === THEN steps ===

@then("I should be redirected to the inventory page")
def verify_inventory_page_loaded(inventory_page):
    assert inventory_page.is_loaded(), \
        f"Expected inventory page, but URL is: {inventory_page.page.url}"


@then(parsers.parse('I should see the page title "{expected_title}"'))
def verify_page_title(inventory_page, expected_title):
    actual = inventory_page.get_page_title_text()
    assert actual == expected_title, \
        f"Expected title '{expected_title}', but got '{actual}'"


@then(parsers.parse('the inventory items should be sorted by name ascending'))
def verify_sorted_by_name_asc(inventory_page):
    actual_product_names = inventory_page.get_product_names()
    expected_product_names = sorted(actual_product_names)
    assert actual_product_names == expected_product_names, \
        f"Products are not sorted by name ascending. Expected: {expected_product_names}, Got: {actual_product_names}"


@then(parsers.parse('the inventory items should be sorted by name descending'))
def verify_sorted_by_name_desc(inventory_page):
    actual_product_names = inventory_page.get_product_names()
    expected_product_names = sorted(actual_product_names, reverse=True)
    assert actual_product_names == expected_product_names, \
        f"Products are not sorted by name descending. Expected: {expected_product_names}, Got: {actual_product_names}"


@then(parsers.parse('the inventory items should be sorted by price ascending'))
def verify_sorted_by_price_asc(inventory_page):
    actual_product_prices = inventory_page.get_product_prices()
    expected_product_prices = sorted(actual_product_prices)
    assert actual_product_prices == expected_product_prices, \
        f"Products are not sorted by price ascending. Expected: {expected_product_prices}, Got: {actual_product_prices}"


@then(parsers.parse('the inventory items should be sorted by price descending'))
def verify_sorted_by_price_desc(inventory_page):
    actual_product_prices = inventory_page.get_product_prices()
    expected_product_prices = sorted(actual_product_prices, reverse=True)
    assert actual_product_prices == expected_product_prices, \
        f"Products are not sorted by price descending. Expected: {expected_product_prices}, Got: {actual_product_prices}"


@then("the inventory items should still be sorted by name descending")
def verify_persistence_name_desc(inventory_page):
    actual_product_names = inventory_page.get_product_names()
    expected_product_names = sorted(actual_product_names, reverse=True)
    assert actual_product_names == expected_product_names, \
        f"Products are not sorted by name descending after action. Expected: {expected_product_names}, Got: {actual_product_names}"


@then("the inventory items should still be sorted by price ascending")
def verify_persistence_price_asc(inventory_page):
    actual_product_prices = inventory_page.get_product_prices()
    expected_product_prices = sorted(actual_product_prices)
    assert actual_product_prices == expected_product_prices, \
        f"Products are not sorted by price ascending after action. Expected: {expected_product_prices}, Got: {actual_product_prices}"


@then("the inventory items should still be sorted by price descending")
def verify_persistence_price_desc(inventory_page):
    actual_product_prices = inventory_page.get_product_prices()
    expected_product_prices = sorted(actual_product_prices, reverse=True)
    assert actual_product_prices == expected_product_prices, \
        f"Products are not sorted by price descending after action. Expected: {expected_product_prices}, Got: {actual_product_prices}"


@then("The cart icon updates to show the number of items")
def verify_cart_badge_updates(inventory_page):
    assert inventory_page.get_cart_badge_text() == "1", \
        "Expected cart badge to show '1' after adding an item."


@then("User is navigated to the cart page")
def verify_on_cart_page(cart_page):
    assert cart_page.is_loaded(), "Expected to be on the cart page."


@then("User is returned to the inventory page")
def verify_returned_to_inventory(inventory_page):
    assert inventory_page.is_loaded(), "Expected to be back on the inventory page."


@then("User is navigated to the product detail page for that item")
def verify_on_product_detail_page(product_detail_page):
    assert product_detail_page.is_loaded(), "Expected to be on the product detail page."


@then("Products are displayed in alphabetical order by name (A to Z)")
def verify_default_sort_is_name_asc(inventory_page):
    # This is a specific case of verify_sorted_by_name_asc
    verify_sorted_by_name_asc(inventory_page)


@then("The sort dropdown closes, and the product list updates to reflect the new sorting order")
def verify_sort_dropdown_closes_and_list_updates(inventory_page):
    # This is implicitly tested by the subsequent assertions that check the sorted order.
    # We can add a check that the dropdown is no longer visible or that its value has changed.
    assert not inventory_page.is_sort_dropdown_open(), "Sort dropdown should be closed."
    # The update is verified by the next step in the scenario.


@then("Products are displayed in order of decreasing price (from highest to lowest)")
def verify_price_high_to_low(inventory_page):
    # This is a specific case of verify_sorted_by_price_desc
    verify_sorted_by_price_desc(inventory_page)


@then("Products are displayed in order of increasing price (from lowest to highest)")
def verify_price_low_to_high(inventory_page):
    # This is a specific case of verify_sorted_by_price_asc
    verify_sorted_by_price_asc(inventory_page)


@then("Products are displayed in reverse alphabetical order by name (Z to A)")
def verify_name_z_to_a(inventory_page):
    # This is a specific case of verify_sorted_by_name_desc
    verify_sorted_by_name_desc(inventory_page)
