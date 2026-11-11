"""Throw-away validation tests (never merged).

E29e: the first attempt's page load meets an unreachable host (an outage
reading), the retry loads the real page.
E14: one scenario red for a reason in the page; the others pass.
"""
import tempfile
from pathlib import Path

from pytest_bdd import given, scenarios, then, when

from config.paths import feature_path

scenarios(str(feature_path("zz_validation_retry_cases")))

_TMP = Path(tempfile.gettempdir())


@then("the throw-away check reaches the home page on its second attempt")
def reaches_home(page, home_page, base_url):
    mark = _TMP / "zz_validation_outage.mark"
    if not mark.exists():
        mark.write_text("1", encoding="utf-8")
        page.goto("https://zz-validation-unreachable.invalid/")
    page.goto(base_url)
    assert home_page.is_loaded()


@given("I open the throw-away Test Cases page")
def open_test_cases(test_cases_page, base_url):
    test_cases_page.open_test_cases(base_url)


@when("I open the throw-away first test case")
def open_first(test_cases_page):
    test_cases_page.open_first_test_case()


@then("the throw-away second test case's steps are shown")
def second_steps_shown(test_cases_page):
    assert test_cases_page.has_visible_steps()
    test_cases_page.open_second_test_case()
    assert test_cases_page.remaining_on_page()
    assert test_cases_page.heading_matches("Test Case 2")
