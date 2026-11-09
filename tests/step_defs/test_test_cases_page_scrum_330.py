"""Step definitions for features/test_cases_page_scrum_330.py.

Binds the single SCRUM-331 scenario to the HomePage and TestCasesPage
page objects. Steps are module-scoped in pytest-bdd, so every phrase the
feature uses is declared here even if an identical phrase exists elsewhere.
"""
from pytest_bdd import given, when, then, parsers, scenarios

from config.paths import feature_path

scenarios(str(feature_path("test_cases_page_scrum_330")))


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


@then("the feedback email link should be shown")
def assert_feedback_email_link(test_cases_page):
    assert test_cases_page.has_feedback_email_link(), "Feedback email link is not shown"
