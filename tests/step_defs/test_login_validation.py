"""
Step definitions for features/login_validation.feature.
Each @given/@when/@then maps an English line to a Python action.
"""
import pytest
from pytest_bdd import scenarios, given, when, then, parsers

from pages.login_page import LoginPage
from pathlib import Path
from config.paths import feature_path


# Bind this test module to the feature file
# Assuming the feature file is named 'login_validation.feature'
scenarios(str(feature_path("login_validation")))


# === Page Object fixtures (created per-test) ===

@pytest.fixture
def login_page(page):
    """Fixture to provide a LoginPage object for each test."""
    return LoginPage(page)


# === GIVEN steps ===

@given("I am on the SauceDemo login page")
def open_login_page(login_page: LoginPage, base_url: str) -> None:
    """Navigate to the SauceDemo login page."""
    login_page.open(base_url)


# === WHEN steps ===

@when("I attempt to log in with an empty username and an empty password")
def login_with_empty_username_and_password(login_page: LoginPage) -> None:
    """Attempt to log in with both username and password fields empty."""
    login_page.login_as("", "")


@when(parsers.parse('I attempt to log in with username "{username}" and an empty password'))
def login_with_empty_password(login_page: LoginPage, username: str) -> None:
    """Attempt to log in with a given username and an empty password."""
    login_page.login_as(username, "")


@when(parsers.parse('I attempt to log in with an empty username and password "{password}"'))
def login_with_empty_username(login_page: LoginPage, password: str) -> None:
    """Attempt to log in with an empty username and a given password."""
    login_page.login_as("", password)


# === THEN steps ===

@then(parsers.parse('I should see the error message "{expected_message}"'))
def verify_error_message(login_page: LoginPage, expected_message: str) -> None:
    """Verify that the expected error message is displayed on the login page."""
    actual = login_page.get_error_message()
    assert actual == expected_message, \
        f"Expected error message '{expected_message}', but got '{actual}'"
