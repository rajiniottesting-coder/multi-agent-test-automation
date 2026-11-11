"""Step definitions for features/test_cases_page.feature.

Binds the Test Cases page scenarios to NavPage and TestCasesPage methods.
Steps are module-scoped, so every phrase the paired feature uses is declared
here. Page-object methods only — no selectors in this file.
"""
from pytest_bdd import given, when, then, scenarios

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


@when("I click the first test case title")
def click_first_test_case(test_cases_page):
    test_cases_page.open_first_test_case()


# ─────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────

@then('the Test Cases page should be headed "Test Cases"')
def assert_test_cases_heading(test_cases_page):
    assert test_cases_page.heading_matches("Test Cases"), (
        f"Expected heading 'Test Cases', got {test_cases_page.heading_text()!r}"
    )


@then("each test case title should be shown as a link")
def assert_titles_are_links(test_cases_page):
    assert test_cases_page.has_title_links(), "No test case title links were shown"
    assert test_cases_page.all_titles_are_links(), (
        "Not every test case title is rendered as a link"
    )


@then("a feedback email link should be displayed")
def assert_feedback_email_link(test_cases_page):
    assert test_cases_page.has_feedback_email_link(), (
        "Feedback email link was not displayed"
    )


@then("the steps for that test case should be displayed")
def assert_steps_displayed(test_cases_page):
    assert test_cases_page.has_visible_steps(), (
        "Expected the test case steps to be displayed after clicking its title"
    )


@then("I should remain on the Test Cases page")
def assert_still_on_test_cases(test_cases_page):
    assert test_cases_page.remaining_on_page(), (
        "Expected to remain on the Test Cases page"
    )
