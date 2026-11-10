"""Step definitions for features/test_cases_page.feature.

Binds the Test Cases page scenarios to page-object methods. Navigation into the
page goes through NavPage (the shared top menu); everything on the page itself
is read through TestCasesPage.

Conventions followed from the reference suite:
  - every step the feature uses is declared in THIS module (steps are
    module-scoped, so a step defined elsewhere is invisible here)
  - step definitions call page-object methods only; no selectors appear here
  - presence is asserted with waiting readers on the page object
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
def click_test_cases_nav(nav_page):
    nav_page.go_to_test_cases()


@when("I click the title of the first test case")
def click_first_test_case_title(test_cases_page):
    test_cases_page.open_first_test_case()


# ─────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────

@then('the Test Cases page should be displayed headed "Test Cases"')
def assert_test_cases_page_heading(test_cases_page):
    assert test_cases_page.is_loaded(), "Test Cases page did not load"
    assert test_cases_page.heading_matches("Test Cases"), (
        f"Expected heading 'Test Cases', got {test_cases_page.heading_text()!r}"
    )


@then("each test case title should be rendered as a clickable link")
def assert_titles_are_links(test_cases_page):
    assert test_cases_page.has_title_links(), "No test case title links were found"
    assert test_cases_page.all_titles_are_links(), (
        "Not every test case title is rendered as a clickable link"
    )


# AI-ORPHAN: no scenario in features/test_cases_page.feature uses this step after SCRUM-354 revised or retired SCRUM-312. Review before deleting.
# @then("the Feedback for Us section should display an email address link")
# def assert_feedback_email_link(test_cases_page):
    # assert test_cases_page.has_feedback_email_link(), (
        # "Expected a Feedback for Us email address link"
    # )


@then("the steps of that test case should be shown")
def assert_steps_shown(test_cases_page):
    assert test_cases_page.has_visible_steps(), (
        "No test case steps are visible after opening the title"
    )


@then("the page should remain the Test Cases page")
def assert_still_on_test_cases_page(test_cases_page):
    assert test_cases_page.remaining_on_page(), (
        "Navigated away from the Test Cases page"
    )


@then('a "Questions or suggestions?" section should be displayed')
def assert_questions_section_displayed(test_cases_page):
    assert "Questions or suggestions?" in test_cases_page.feedback_section_text(), (
        "Expected a 'Questions or suggestions?' section to be displayed"
    )


@then('the "Feedback for Us" heading should not be shown')
def assert_feedback_for_us_heading_absent(test_cases_page):
    assert "Feedback for Us" not in test_cases_page.feedback_section_text(), (
        "The 'Feedback for Us' heading should not be shown"
    )


@then('the feedback link should read "Write to our QA team"')
def assert_feedback_link_text(test_cases_page):
    assert test_cases_page.feedback_link_text() == "Write to our QA team", (
        f"Expected feedback link text 'Write to our QA team', got "
        f"{test_cases_page.feedback_link_text()!r}"
    )


@then('"feedback@automationexercise.com" should not be shown as the visible link text')
def assert_feedback_email_not_visible_text(test_cases_page):
    assert "feedback@automationexercise.com" not in test_cases_page.feedback_link_text(), (
        "'feedback@automationexercise.com' should not be shown as the visible link text"
    )


@then('the feedback link should still point to "feedback@automationexercise.com"')
def assert_feedback_link_href(test_cases_page):
    assert "feedback@automationexercise.com" in test_cases_page.feedback_link_href(), (
        "Feedback link should still point to 'feedback@automationexercise.com', got "
        f"{test_cases_page.feedback_link_href()!r}"
    )
