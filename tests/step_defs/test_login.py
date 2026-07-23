"""
Step definitions for features/login.feature.

REFERENCE FILE — the gold-standard example Agent 2 copies. Follow this shape.

THE ONE RULE
------------
A step-def module is SELF-CONTAINED: it declares EVERY step its own feature
file uses. Do not rely on steps defined in another step-def module — pytest-bdd
step definitions are module-scoped fixtures, so another module's steps are
invisible here and the test would fail at collection with
StepDefinitionNotFoundError.

Declaring the same step text as another module is SAFE and expected. Each
module resolves its own copy; they never collide. So there is no judgement to
make about which steps are "shared" — you simply write the ones your feature
needs.

Page-object FIXTURES are the exception: they come from
tests/step_defs/conftest.py, because fixtures do resolve hierarchically.

CONVENTIONS TO COPY
-------------------
- Step functions call PAGE OBJECT methods only. Never use a selector, and never
  read a selector constant, in a step definition.
- Keep each decorator's pattern on ONE single-quoted line. The step-coverage
  validator reads from the first quote to the last quote, so splitting a
  pattern across lines corrupts it and every step using it stops matching.
- Use parsers.re with [^"]* for any quoted placeholder whose value could be
  empty. parsers.parse cannot match "" — validation scenarios rely on this.
- Assertions carry expected-vs-actual, so a CI failure is readable without
  re-running locally.
"""
from pytest_bdd import scenarios, given, when, then, parsers

from config.paths import feature_path


# Bind this module to its feature file.
scenarios(str(feature_path("login")))


# === GIVEN steps ===

@given("I am on the SauceDemo login page")
def open_login_page(login_page, base_url):
    login_page.open(base_url)


# === WHEN steps ===

@when(parsers.re(r'I log in with username "(?P<username>[^"]*)" and password "(?P<password>[^"]*)"'))
def login_with_credentials(login_page, username, password):
    login_page.login_as(username, password)


@when("I dismiss the error message")
def dismiss_error_banner(login_page):
    login_page.dismiss_error()


@when("I clear the credential fields")
def clear_credential_fields(login_page):
    login_page.clear_credentials()


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


@then("no error message should be displayed")
def verify_no_error_message(login_page):
    actual = login_page.get_error_message()
    assert actual == "", \
        f"Expected no error message, but got '{actual}'"