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


# AI-ORPHAN: no scenario in features/test_cases_page_scrum_330.feature uses this step after SCRUM-360 revised or retired SCRUM-331. Review before deleting.
# @then("the feedback email link should be shown")
# def assert_feedback_email_link(test_cases_page):
    # assert test_cases_page.has_feedback_email_link(), "Feedback email link is not shown"


@then("the feedback email link should not be shown")
def assert_feedback_email_link_absent(test_cases_page):
    assert test_cases_page.is_feedback_email_link_absent(), "Feedback email link is shown"


@when("I click the feedback Contact us link")
def click_feedback_contact_us(test_cases_page):
    test_cases_page.click_feedback_contact_us()


@then("I should be on the Contact Us page")
def assert_on_contact_us_page(contact_us_page):
    assert contact_us_page.is_loaded(), "Not on the Contact Us page"


@then("the Contact Us form should be shown")
def assert_contact_us_form_shown(contact_us_page):
    assert contact_us_page.is_contact_form_shown(), "Contact Us form is not shown"


@then("a new browser tab should not be opened")
def assert_no_new_tab_opened(test_cases_page):
    assert test_cases_page.no_new_tab_opened(), "A new browser tab was opened"
