"""Step definitions for features/test_cases_page.feature.

Binds the Test Cases page scenarios to page-object methods. Every step the
feature uses is declared here — steps are module-scoped, so a step defined in
another module is not visible to this one. No selectors appear here; the step
definitions interact with the UI only through page-object methods.
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


@when("I click the title of the first test case")
def click_first_test_case(test_cases_page):
    test_cases_page.open_first_test_case()


@when("I click the title of the second test case")
def click_second_test_case(test_cases_page):
    test_cases_page.open_second_test_case()


# ─────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────

@then('the Test Cases page should be headed "Test Cases"')
def assert_heading(test_cases_page):
    assert test_cases_page.heading_matches("Test Cases"), (
        f"Expected the Test Cases heading, got {test_cases_page.heading_text()!r}"
    )


@then("each test case title should be shown as a link")
def assert_titles_are_links(test_cases_page):
    assert test_cases_page.has_title_links(), "Expected test case titles to be shown"
    assert test_cases_page.all_titles_are_links(), (
        "Expected every test case title to be rendered as a link"
    )


@then("the steps for the first test case should be shown")
def assert_first_steps_shown(test_cases_page):
    assert test_cases_page.has_visible_steps(), (
        "Expected the first test case's steps to be shown"
    )


@then("the steps for the second test case should be shown")
def assert_second_steps_shown(test_cases_page):
    assert test_cases_page.has_visible_steps(), (
        "Expected the second test case's steps to be shown"
    )


@then("I should remain on the Test Cases page")
def assert_remain_on_page(test_cases_page):
    assert test_cases_page.remaining_on_page(), (
        "Expected to remain on the Test Cases page"
    )
