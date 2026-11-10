"""Step definitions for features/api_testing_nav_link.feature.

Binds the API Testing navigation-link scenarios to page-object methods.
Every step the feature uses is declared here, because pytest-bdd steps are
module-scoped and a step defined elsewhere is not visible to this module.
Step definitions call page-object methods only — never a selector.
"""
from pytest_bdd import given, when, then, scenarios

from config.paths import feature_path

scenarios(str(feature_path("api_testing_nav_link")))


# ─────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────

@given("I am on the home page")
def open_home_page(home_page, base_url):
    home_page.open_home_page(base_url)


# ─────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────

@when("I navigate to the Contact Us page")
def navigate_to_contact_us(api_nav_page):
    api_nav_page.navigate_to_contact_us()


@when("I click the API Testing link")
def click_api_testing_link(api_nav_page):
    api_nav_page.click_api_testing_link()


# ─────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────

@then("I should see the Test Cases link in the top navigation")
def assert_test_cases_link_shown(api_nav_page):
    assert api_nav_page.is_test_cases_link_shown(), \
        "Expected the Test Cases link in the top navigation"


@then("I should see the API Testing link in the top navigation")
def assert_api_testing_link_shown(api_nav_page):
    assert api_nav_page.is_api_testing_link_shown(), \
        "Expected the API Testing link in the top navigation"


@then("I should be taken to the API testing page")
def assert_taken_to_api_testing(api_nav_page):
    assert api_nav_page.has_left_page("/contact_us"), \
        "Expected to navigate away after clicking the API Testing link"
