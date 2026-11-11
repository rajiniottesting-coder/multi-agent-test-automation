"""Step definitions for features/test_cases_page_navigation.feature.

Covers SCRUM-331: opening the Test Cases page from the home page button, then
confirming the heading, the list of test case title links, and the feedback
email address link.

The "I should be on the Test Cases page", "the page should be headed ..." and
"a list of test case titles should be displayed" phrases are also declared in
tests/step_defs/test_test_cases_page_scrum_330.py. pytest-bdd steps are
module-scoped, so they are re-declared here and assert exactly what the
committed definitions assert.
"""
from pytest_bdd import given, when, then, parsers, scenarios

from config.paths import feature_path

scenarios(str(feature_path("test_cases_page_navigation")))


# ─────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────

@given("I am on the home page")
def open_home_page(home_page, base_url):
    home_page.open_home_page(base_url)


# ─────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────

@when("I click the Test Cases button on the home page")
def click_test_cases_button(home_page):
    home_page.go_to_test_cases()


# ─────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────

@then("I should be on the Test Cases page")
def assert_on_test_cases_page(test_cases_page):
    assert test_cases_page.is_on_test_cases_page(), "Not on the Test Cases page"


@then(parsers.parse('the page should be headed "{expected}"'))
def assert_page_heading(test_cases_page, expected):
    assert test_cases_page.heading_matches(expected), (
        f"Expected heading {expected!r}, got {test_cases_page.heading_text()!r}"
    )


@then("a list of test case titles should be displayed")
def assert_titles_displayed(test_cases_page):
    assert test_cases_page.has_title_links(), "No test case title links are displayed"
    assert test_cases_page.all_titles_are_links(), "Not every test case title is a link"


@then("the feedback email address link should be shown")
def assert_feedback_email_link(test_cases_page):
    assert test_cases_page.has_feedback_email_link(), (
        "The feedback email address link is not shown"
    )
