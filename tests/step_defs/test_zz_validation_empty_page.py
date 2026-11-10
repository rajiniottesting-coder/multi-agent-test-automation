"""Throw-away validation test (never merged): its first step clicks before any
page is opened, so it must fail at once with "No page is open" (E56)."""
from pytest_bdd import scenarios, then, when

from config.paths import feature_path

scenarios(str(feature_path("zz_validation_empty_page")))


@when("I click the Test Cases link in the top menu straight away")
def click_test_cases(nav_page):
    nav_page.go_to_test_cases()


@then("the throw-away Test Cases page is shown")
def test_cases_shown(test_cases_page):
    assert test_cases_page.is_loaded()
