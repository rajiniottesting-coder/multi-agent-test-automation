"""Step definitions for features/test_cases_search.feature.

Binds the Test Cases search scenarios to TestCasesPage methods. Selectors live
in the inventory and are reached only through page-object methods here.

- Presence is asserted with waiting readers (is_title_shown, is_title_a_link).
- Absence is asserted with non-waiting predicates (is_title_hidden,
  has_no_titles) so the assertion is reached instead of timing out.
"""
from pytest_bdd import given, when, then, parsers, scenarios

from config.paths import feature_path

scenarios(str(feature_path("test_cases_search")))


# ─────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────

@given("I am on the Test Cases page")
def open_test_cases(test_cases_page, base_url):
    test_cases_page.open_test_cases(base_url)


# ─────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────

@when(parsers.re(r'I search the test cases for "(?P<term>[^"]*)"'))
def search_test_cases(test_cases_page, term):
    test_cases_page.search_for(term)


@when("I clear the test case search box")
def clear_test_case_search(test_cases_page):
    test_cases_page.clear_search()


# ─────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────

@then("the full list of test case titles is displayed")
def assert_full_list(test_cases_page):
    assert test_cases_page.has_titles(), "Expected the Test Cases list to show titles"


@then(parsers.re(r'the test case title "(?P<title>[^"]*)" is shown as a link'))
def assert_title_is_link(test_cases_page, title):
    assert test_cases_page.is_title_a_link(title), (
        f"Expected title {title!r} to be shown as a clickable link"
    )


@then(parsers.re(r'every shown test case title contains "(?P<term>[^"]*)"'))
def assert_every_title_contains(test_cases_page, term):
    assert test_cases_page.every_title_contains(term), (
        f"Expected every shown title to contain {term!r}"
    )


@then(parsers.re(r'the test case title "(?P<title>[^"]*)" should not be shown'))
def assert_title_not_shown(test_cases_page, title):
    assert test_cases_page.is_title_hidden(title), (
        f"Expected title {title!r} not to be shown"
    )


@then("no test case titles are shown")
def assert_no_titles(test_cases_page):
    assert test_cases_page.has_no_titles(), "Expected no test case titles to be shown"


@then(parsers.re(r'the test case title "(?P<title>[^"]*)" is shown'))
def assert_title_shown(test_cases_page, title):
    assert test_cases_page.is_title_shown(title), (
        f"Expected title {title!r} to be shown"
    )
