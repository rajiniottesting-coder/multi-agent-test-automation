"""Step definitions for features/contact_us_validation.feature.

Binds the contact_us_validation scenario to ContactUsPage methods. Covers
SCRUM-310: an empty Subject must stop the form from submitting, so no success
message appears and the visitor stays on the Contact Us page.

Conventions (see pages/login_page.py and tests/step_defs/test_login.py):
- call page-object methods only; never put a selector in a step definition
- use parsers.re with [^"]* where a quoted value can be empty (the subject is)
- assert ABSENCE with a non-waiting predicate, never a waiting getter
"""
from pytest_bdd import given, when, then, parsers, scenarios

from config.paths import feature_path

scenarios(str(feature_path("contact_us_validation")))


# ─────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────

@given("I am on the Contact Us page")
def open_contact_us(contact_us_page, base_url):
    contact_us_page.open_contact_us(base_url)


# ─────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────

@when(parsers.re(
    r'I fill in the contact form with name "(?P<name>[^"]*)", '
    r'email "(?P<email>[^"]*)", subject "(?P<subject>[^"]*)" '
    r'and message "(?P<message>[^"]*)"'
))
def fill_contact_form(contact_us_page, name, email, subject, message):
    contact_us_page.fill_contact_form(name, email, subject, message)


@when("I submit the contact form")
def submit_contact_form(contact_us_page):
    contact_us_page.submit_contact_form()


# ─────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────

@then("no contact success message should be shown on the Contact Us page")
def assert_no_success_message(contact_us_page):
    assert contact_us_page.is_success_message_absent(), \
        "Contact success message was shown, but the form should have been rejected"


@then("I should remain on the Contact Us page")
def assert_still_on_contact_us(contact_us_page):
    assert contact_us_page.is_loaded(), "Expected to stay on the Contact Us page"
