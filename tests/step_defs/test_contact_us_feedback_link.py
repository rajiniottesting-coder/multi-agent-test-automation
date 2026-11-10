"""Step definitions for features/contact_us_feedback_link.feature (SCRUM-366).

Binds the Contact Us feedback-link scenario to ContactUsPage query methods.
The feedback link must still display the email address as its link text and
still be a mailto: link, unaffected by the Test Cases page rename.

Conventions (see tests/step_defs/test_login.py):
  - Declare every step the feature uses in THIS file.
  - Call page-object methods only; never a selector here.
  - Assert exactly what each sentence promises.
"""
from pytest_bdd import given, when, then, scenarios

from config.paths import feature_path

scenarios(str(feature_path("contact_us_feedback_link")))


# ─────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────

@given("I am on the home page")
def open_home_page(home_page, base_url):
    home_page.open_home_page(base_url)


# ─────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────

@when("I click the Contact Us link in the navigation")
def click_contact_us(nav_page):
    nav_page.go_to_contact_us()


# ─────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────

@then("the Contact Us page should be shown")
def assert_contact_us_shown(contact_us_page):
    assert contact_us_page.is_loaded(), "Expected the Contact Us page to be shown"


@then("the feedback email link should display the email address as its link text")
def assert_feedback_link_text(contact_us_page):
    link_text = contact_us_page.get_feedback_email_link_text()
    assert link_text == "feedback@automationexercise.com", (
        "Expected the feedback link text to be the email address "
        f"'feedback@automationexercise.com', got {link_text!r}"
    )


@then("the feedback email link should be a mailto link")
def assert_feedback_link_mailto(contact_us_page):
    href = contact_us_page.get_feedback_email_link_href()
    assert href.startswith("mailto:"), (
        f"Expected the feedback link href to be a mailto: link, got {href!r}"
    )
