"""Step definitions for features/test_cases_page_scrum_330.feature.

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


# AI-ORPHAN: no scenario in features/test_cases_page_scrum_330.feature uses this step after SCRUM-354 revised or retired SCRUM-331. Review before deleting.
# @then("the feedback email link should be shown")
# def assert_feedback_email_link(test_cases_page):
    # assert test_cases_page.has_feedback_email_link(), "Feedback email link is not shown"


@then(parsers.parse('the feedback section should be headed "{expected}"'))
def assert_feedback_heading(test_cases_page, expected):
    assert test_cases_page.feedback_heading_matches(expected), (
        f"Expected feedback heading {expected!r}, got {test_cases_page.feedback_heading_matches(expected)!r}"
    )


@then(parsers.parse('the heading "{heading}" should not be shown'))
def assert_heading_absent(test_cases_page, heading):
    assert test_cases_page.feedback_heading_is_absent(heading), (
        f"Heading {heading!r} should not be shown"
    )


@then(parsers.parse('the feedback email link should read "{expected}"'))
def assert_feedback_link_text(test_cases_page, expected):
    assert test_cases_page.feedback_link_text() == expected, (
        f"Expected feedback link text {expected!r}, got {test_cases_page.feedback_link_text()!r}"
    )


@then("the raw email address should not be shown as the feedback link text")
def assert_raw_email_not_link_text(test_cases_page):
    href = test_cases_page.feedback_link_href()
    raw_email = href.replace("mailto:", "")
    assert raw_email not in test_cases_page.feedback_link_text(), (
        f"Raw email address {raw_email!r} should not be shown as the feedback link text"
    )


@then("the feedback email link should still point to the same mailto address")
def assert_feedback_link_href(test_cases_page):
    href = test_cases_page.feedback_link_href()
    assert href.startswith("mailto:"), (
        f"Expected feedback link to point to a mailto address, got {href!r}"
    )
