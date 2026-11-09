"""Step definitions for features/test_cases_page.feature.

Binds the Test Cases page navigation scenario. Interacts with the UI
exclusively through page-object methods; no selectors appear here.
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
    assert home_page.is_loaded(), "Home page did not load"


# ─────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────

@when("I click the Test Cases button on the home page")
def click_test_cases_button(home_page):
    home_page.click_test_cases_button()


# ─────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────

@then("I should be on the Test Cases page")
def assert_on_test_cases_page(test_cases_page):
    assert test_cases_page.is_loaded(), "Not on the Test Cases page"


@then('the page should be headed "Test Cases"')
def assert_heading(test_cases_page):
    assert test_cases_page.heading_matches("Test Cases"), (
        f"Expected heading 'Test Cases', got {test_cases_page.heading_text()!r}"
    )


@then("a list of test case titles should be shown as links")
def assert_titles_are_links(test_cases_page):
    assert test_cases_page.has_title_links(), "No test case title links are shown"
    assert test_cases_page.all_titles_are_links(), (
        "Not all test case titles are rendered as links"
    )


@then("the feedback email address link should be shown")
def assert_feedback_email_link(test_cases_page):
    assert test_cases_page.has_feedback_email_link(), (
        "The feedback email address link is not shown"
    )
