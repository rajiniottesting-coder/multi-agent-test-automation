"""Shared page-object fixtures and shared step definitions.

WHY THIS FILE EXISTS (read before moving anything out of it)
------------------------------------------------------------
pytest-bdd implements step definitions as pytest FIXTURES. Fixtures are
module-scoped: a step defined in `tests/step_defs/test_login.py` is visible
ONLY inside that module. It is NOT available to any other step-def module.

That means a generated feature (e.g. features/login_edge_validation.feature)
whose scenarios reuse a step like `Given I am on the SauceDemo login page`
will fail at collection with:

    pytest_bdd.exceptions.StepDefinitionNotFoundError

unless that step lives in a conftest.py. Fixtures (and therefore steps)
defined in conftest.py ARE shared with every test module in this directory
and below — that is the only supported cross-module reuse mechanism.

So: any step or fixture that MORE THAN ONE feature file needs belongs here.
Steps that are genuinely specific to one feature belong in that feature's
paired step-def module.

FORMATTING RULE (do not break this)
-----------------------------------
Keep each decorator's pattern on ONE single-quoted line. The step-coverage
validator extracts decorators with a regex that reads from the first quote to
the last quote; splitting a pattern across lines with implicit string
concatenation corrupts the captured pattern and makes EVERY step using it
fail to match.

WHY parsers.re AND NOT parsers.parse FOR QUOTED VALUES
------------------------------------------------------
Validation scenarios pass empty values, e.g.:

    When I log in with username "" and password ""

`parsers.parse('... "{username}" ...')` looks like it should match that, but
it does not: the underlying `parse` library's default placeholder requires at
least one character, so empty quoted values fail at runtime.
`parsers.re(r'... "(?P<username>[^"]*)" ...')` accepts zero or more non-quote
characters, matching both "alice" and "". Named groups bind to the function
arguments exactly like parsers.parse does.

RULE: any quoted placeholder whose value could legitimately be empty must use
parsers.re with [^"]*.
"""
import pytest
from pytest_bdd import given, when, then, parsers

from pages.login_page import LoginPage
from pages.inventory_page import InventoryPage


# === Shared page-object fixtures (created per-test) ===

@pytest.fixture
def login_page(page):
    return LoginPage(page)


@pytest.fixture
def inventory_page(page):
    return InventoryPage(page)


# === Shared GIVEN steps ===

@given("I am on the SauceDemo login page")
def open_login_page(login_page, base_url):
    login_page.open(base_url)


# === Shared WHEN steps ===

@when(parsers.re(r'I log in with username "(?P<username>[^"]*)" and password "(?P<password>[^"]*)"'))
def login_with_credentials(login_page, username, password):
    login_page.login_as(username, password)


# === Shared THEN steps ===

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