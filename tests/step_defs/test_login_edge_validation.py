"""
Step definitions for features/login_edge_validation.feature.

Implements steps for error dismissal, field clearing, multi-attempt login flows,
and inventory item count verification.

Steps already defined in test_login.py (reused, NOT redefined here):
- Given I am on the SauceDemo login page
- When I log in with username "..." and password "..."
- Then I should see the error message "..."
- Then I should be redirected to the inventory page
"""
import pytest
from pytest_bdd import scenarios, given, when, then, parsers

from pages.login_page import LoginPage
from pages.inventory_page import InventoryPage
from config.paths import feature_path


# Bind this test module to the feature file
scenarios(str(feature_path("login_edge_validation")))


# === Page Object fixtures (created per-test) ===

@pytest.fixture
def login_page(page) -> LoginPage:
    return LoginPage(page)


@pytest.fixture
def inventory_page(page) -> InventoryPage:
    return InventoryPage(page)


# === WHEN steps ===

@when("I dismiss the error message")
def dismiss_error(login_page: LoginPage) -> None:
    login_page.dismiss_error()


@when("I clear the login form")
def clear_login_form(login_page: LoginPage) -> None:
    login_page.clear_credentials()


# === THEN steps ===

@then("the error message should be dismissed")
def verify_error_dismissed(login_page: LoginPage) -> None:
    error_text = login_page.get_error_message()
    assert error_text == "", \
        f"Expected error to be dismissed, but found: '{error_text}'"


@then(parsers.parse('I should see {expected_count:d} inventory items'))
def verify_inventory_item_count(inventory_page: InventoryPage, expected_count: int) -> None:
    actual_count = inventory_page.get_inventory_item_count()
    assert actual_count == expected_count, \
        f"Expected {expected_count} inventory items, but found {actual_count}"
