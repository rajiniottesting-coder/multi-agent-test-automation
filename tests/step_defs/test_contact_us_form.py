"""Step definitions for features/contact_us_form.feature.

Binds the Contact Us scenarios to ContactUsPage, NavPage and HomePage methods.

Conventions followed:
- Declare EVERY step the paired feature uses in this module; steps are
  module-scoped and are not inherited from other step-def files.
- Call page-object methods only; no selectors appear here.
- The email value can be empty ("") for the negative scenario, so the
  fill step uses parsers.re with [^"]* placeholders — parsers.parse cannot
  match an empty quoted value.
- Assert PRESENCE with the waiting reader (has_success_message); assert
  ABSENCE with the non-waiting probe (is_success_message_absent).
"""
from urllib.parse import urlsplit

from pytest_bdd import given, when, then, parsers, scenarios

from config.paths import feature_path

scenarios(str(feature_path("contact_us_form")))


# ─────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────

@given("I am on the Contact Us page")
def open_contact_us(contact_us_page, nav_page, base_url):
    """Reach the Contact Us page via the top-nav Contact us link."""
    nav_page.go_to_contact_us()
    assert contact_us_page.is_loaded(), "Contact Us page did not load"


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


@when("I click the Home button")
def click_home_button(contact_us_page):
    contact_us_page.click_home_button()


# ─────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────

@then("I should see the contact success message")
def assert_success_shown(contact_us_page):
    """Waiting reader: the success banner is expected to appear."""
    assert contact_us_page.has_success_message(), \
        "Expected the contact success message to be shown"


@then("I should not see the contact success message")
def assert_success_absent(contact_us_page):
    """Non-waiting probe: absence is the expected case, so nothing may wait."""
    assert contact_us_page.is_success_message_absent(), \
        "Contact success message was shown but should not be"


@then("I should be returned to the home page")
def assert_on_home_page(home_page, base_url):
    assert home_page.is_loaded(), "Expected to be returned to the home page"
    current = urlsplit(home_page.page.url)
    expected = urlsplit(base_url)
    assert current.netloc == expected.netloc, \
        f"Expected home host {expected.netloc!r}, got {current.netloc!r}"
    assert current.path.rstrip("/") == expected.path.rstrip("/"), \
        f"Expected home path, got {current.path!r}"


@then("I should remain on the Contact Us page")
def assert_still_on_contact_us(contact_us_page):
    assert contact_us_page.is_loaded(), "Expected to stay on the Contact Us page"
