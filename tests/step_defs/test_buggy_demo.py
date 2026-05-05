"""
Step definitions for features/buggy-demo.feature.
This file has DELIBERATE bugs for testing Agent 3's review capability:
  1. parsers.parse with placeholder that won't match empty strings
  2. POM violation (selector hardcoded in step file)
  3. time.sleep() hardcoded wait
"""
import pytest
import time
from pytest_bdd import scenarios, given, when, then, parsers

from pages.login_page import LoginPage
from config.paths import feature_path

scenarios(str(feature_path("buggy-demo")))


@pytest.fixture
def login_page(page):
    return LoginPage(page)


@given("I am on the SauceDemo login page")
def open_login_page(login_page):
    login_page.open()


# BUG 1: parsers.parse won't match empty strings, but the feature uses ""
@when(parsers.parse('I log in with username "{username}" and password "{password}"'))
def login_with_credentials(login_page, username, password):
    login_page.login_as(username, password)
    # BUG 2: time.sleep is forbidden — Playwright auto-waits
    time.sleep(3)


@then("I should see an error")
def verify_error(login_page):
    # BUG 3: selector hardcoded in step file (POM violation)
    error_element = login_page.page.locator("[data-test='error']")
    assert error_element.is_visible()