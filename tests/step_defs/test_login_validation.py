"""
Step definitions for features/login-validation.feature.
This file implements validation scenarios for the login page,
such as empty username or password fields.
"""
import pytest
from pytest_bdd import scenarios, given, when, then, parsers

from pages.login_page import LoginPage
from pathlib import Path
from config.paths import feature_path


# Bind this test module to the feature file
scenarios(str(feature_path("login-validation")))


# === Page Object fixtures (created per-test) ===

@pytest.fixture
def login_page(page):
    """Fixture for the LoginPage object."""
    return LoginPage(page)


# === GIVEN steps ===

@given("I am on the SauceDemo login page")
def open_login_page(login_page, base_url):
    """Navigate to the SauceDemo login page."""
    login_page.open(base_url)


# === WHEN steps ===

@when("I attempt to log in with an empty username and password")
def login_with_empty_credentials(login_page):
    """Attempt to log in with both username and password fields empty."""
    login_page.login_as("", "")


@when(parsers.parse('I attempt to log in with username "{username}" and an empty password'))
def login_with_empty_password(login_page, username):
    """Attempt to log in with a given username and an empty password."""
    login_page.login_as(username, "")


@when(parsers.parse('I attempt to log in with an empty username and password "{password}"'))
def login_with_empty_username(login_page, password):
    """Attempt to log in with an empty username and a given password."""
    login_page.login_as("", password)


# === THEN steps ===

@then(parsers.parse('I should see the error message "{expected_message}"'))
def verify_error_message(login_page, expected_message):
    """Verify that the expected error message is displayed."""
    actual = login_page.get_error_message()
    assert actual == expected_message, \
        f"Expected error '{expected_message}', but got '{actual}'"
