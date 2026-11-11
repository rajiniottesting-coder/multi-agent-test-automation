"""Step definitions for features/test_cases_page.feature.

Binds the Test Cases scenarios to NavPage and TestCasesPage methods.

Conventions followed (see pages/login_page.py and tests/step_defs/test_login.py):
- Every step the feature uses is declared here; steps are module-scoped.
- Step definitions call page-object methods only; no selectors appear here.
- Presence is asserted with waiting readers; staying-on-page is checked with a
  waiting readiness probe on the destination page object.
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
def click_first_test_case(test_cases_page):
    test_cases_page.open_first_test_case()


# ─────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────

@then(parsers.re(r'the Test Cases page should be headed "(?P<expected>[^"]*)"'))
def assert_heading(test_cases_page, expected):
    assert test_cases_page.heading_matches(expected), (
        f"Expected the Test Cases heading to match {expected!r}, "
        f"got {test_cases_page.heading_text()!r}"
    )


@then("each test case title should be shown as a link")
def assert_titles_are_links(test_cases_page):
    assert test_cases_page.has_title_links(), "No test case title links are shown"
    assert test_cases_page.all_titles_are_links(), (
        "Not every test case title is rendered as a link"
    )


@then("the Feedback for Us section should show an email address link")
def assert_feedback_email_link(test_cases_page):
    assert test_cases_page.has_feedback_email_link(), (
        "Expected the Feedback for Us section to show an email address link"
    )


@then("the steps of that test case should be displayed")
def assert_steps_displayed(test_cases_page):
    assert test_cases_page.has_visible_steps(), (
        "Expected the test case's steps to be displayed underneath its title"
    )


@then("I should remain on the Test Cases page")
def assert_still_on_test_cases(test_cases_page):
    assert test_cases_page.is_on_test_cases_page(), (
        "Expected to remain on the Test Cases page"
    )
