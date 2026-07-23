"""
Step definitions for features/login.feature.
Each @given/@when/@then maps an English line to a Python action.

REFERENCE FILE — this is the gold-standard example Agent 2 copies when it
generates new step definitions. Keep it small, correct, and idiomatic:
every convention shown here is one the LLM will reproduce.

WHY parsers.re INSTEAD OF parsers.parse FOR QUOTED VALUES
---------------------------------------------------------
pytest-bdd registers step decorators GLOBALLY for the test session, so the
steps defined here are reused by every other feature file — including
generated validation scenarios that pass EMPTY values, e.g.:

    When I log in with username "" and password ""

`parsers.parse('... "{username}" ...')` looks like it should match that, but
it does NOT: the underlying `parse` library's default placeholder requires at
least one character, so empty quoted values fail at runtime with
StepDefinitionNotFoundError.

`parsers.re(r'... "(?P<username>[^"]*)" ...')` accepts zero or more non-quote
characters, so it matches both "alice" and "". Named groups bind to the
function arguments exactly like parsers.parse does, so nothing else changes.

RULE: any quoted placeholder whose value could legitimately be empty must use
parsers.re with [^"]*.

FORMATTING RULE (do not break this): keep each decorator's pattern on ONE
single-quoted line. The step-coverage validator extracts decorators with a
regex that reads from the first quote to the last quote, so splitting a
pattern across lines with implicit string concatenation corrupts the captured
pattern and makes EVERY step using it fail to match.
"""
import pytest
from pytest_bdd import scenarios, given, when, then, parsers

from pages.login_page import LoginPage
from pages.inventory_page import InventoryPage
from pathlib import Path
from config.paths import feature_path


# Bind this test module to the feature file
scenarios(str(feature_path("login")))


# === Page Object fixtures (created per-test) ===

@pytest.fixture
def login_page(page):
    return LoginPage(page)


@pytest.fixture
def inventory_page(page):
    return InventoryPage(page)


# === GIVEN steps ===

@given("I am on the SauceDemo login page")
def open_login_page(login_page, base_url):
    login_page.open(base_url)


# === WHEN steps ===

# parsers.re (not parsers.parse) so empty credentials — used by required-field
# validation scenarios — still match at runtime. See module docstring.
@when(parsers.re(r'I log in with username "(?P<username>[^"]*)" and password "(?P<password>[^"]*)"'))
def login_with_credentials(login_page, username, password):
    login_page.login_as(username, password)


# === THEN steps ===

@then("I should be redirected to the inventory page")
def verify_inventory_page(inventory_page):
    assert inventory_page.is_loaded(), \
        f"Expected inventory page, but URL is: {inventory_page.page.url}"


@then(parsers.re(r'I should see the page title "(?P<expected_title>[^"]*)"'))
def verify_page_title(inventory_page, expected_title):
    actual = inventory_page.get_page_title_text()
    assert actual == expected_title, \
        f"Expected title '{expected_title}', but got '{actual}'"


@then(parsers.re(r'I should see the error message "(?P<expected_message>[^"]*)"'))
def verify_error_message(login_page, expected_message):
    actual = login_page.get_error_message()
    assert actual == expected_message, \
        f"Expected error '{expected_message}', but got '{actual}'"