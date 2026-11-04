"""Step definitions for features/test_cases_page.feature.

Binds the Test Cases page scenarios to page-object calls only. No selectors
live here — every UI interaction and every read goes through a page-object
method. Steps are module-scoped, so each phrase the feature uses is declared
in this file.
"""
from pytest_bdd import given, when, then, parsers, scenarios

from config.paths import feature_path

scenarios(str(feature_path("test_cases_page")))


# ─────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────

@given("I am on the home page")
def open_home_page(home_page, base_url):
    home_page.open_home_page(base_url)


# ─────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────

@when('I click "Test Cases" in the top navigation menu')
def click_test_cases_in_nav(nav_page):
    nav_page.go_to_test_cases()


@when("I click the first test case title")
def click_first_test_case(test_cases_page):
    test_cases_page.open_first_test_case()


# ─────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────

@then(parsers.parse('the Test Cases page should be displayed with the heading "{heading}"'))
def assert_test_cases_heading(test_cases_page, heading):
    assert test_cases_page.is_loaded(), "Test Cases page did not load"
    actual = test_cases_page.heading_text()
    assert heading in actual, f"Expected heading {heading!r} in {actual!r}"


@then("each test case title should be rendered as a link")
def assert_titles_are_links(test_cases_page):
    assert test_cases_page.has_title_links(), "No test case title links were found"
    assert test_cases_page.all_titles_are_links(), "Not every test case title is a link"


@then("the steps for that test case should be shown")
def assert_steps_shown(test_cases_page):
    assert test_cases_page.has_visible_steps(), "No steps are shown for the test case"


@then("I should remain on the Test Cases page")
def assert_still_on_test_cases(test_cases_page):
    assert test_cases_page.is_loaded(), "Expected to remain on the Test Cases page"
