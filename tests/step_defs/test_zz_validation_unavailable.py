"""Step definitions for the Test Cases page heading check."""
from pytest_bdd import given, parsers, scenarios, then

from config.paths import feature_path

scenarios(str(feature_path("zz_validation_unavailable")))


@given("I open the Test Cases page")
def open_test_cases(test_cases_page, base_url):
    test_cases_page.open_test_cases(base_url)


@then(parsers.parse('the Test Cases page heading reads "{expected}"'))
def heading_reads(test_cases_page, expected):
    assert test_cases_page.heading_text() == expected, f"heading is not {expected!r}"
