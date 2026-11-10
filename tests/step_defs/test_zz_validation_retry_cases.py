"""Throw-away validation tests (never merged).

E29e: the first attempt's page load meets an unreachable host (an outage
reading), the retry loads the real page.
E29g: the heading check expects a different heading on its first attempt.
"""
import tempfile
from pathlib import Path

from pytest_bdd import given, scenarios, then

from config.paths import feature_path

scenarios(str(feature_path("zz_validation_retry_cases")))

_TMP = Path(tempfile.gettempdir())


@then("the throw-away check reaches the home page on its second attempt")
def reaches_home(page, base_url):
    mark = _TMP / "zz_validation_outage.mark"
    if not mark.exists():
        mark.write_text("1", encoding="utf-8")
        page.goto("https://zz-validation-unreachable.invalid/")
    page.goto(base_url)


@given("I open the throw-away Test Cases page")
def open_test_cases(test_cases_page, base_url):
    test_cases_page.open_test_cases(base_url)


@then("the throw-away Test Cases heading reads as expected")
def heading_reads(test_cases_page):
    mark = _TMP / "zz_validation_heading.mark"
    expected = "Test Cases" if mark.exists() else "All Test Scenarios"
    mark.write_text("1", encoding="utf-8")
    assert test_cases_page.heading_matches(expected), f"heading is not {expected!r}"
