"""Step definitions for features/contact_us_no_upload.feature.

Binds the Contact Us (no-upload) scenario to ContactUsPage, HomePage and
NavPage methods. Every step the feature uses is declared here, because
pytest-bdd steps are module-scoped.
"""
from urllib.parse import urlsplit

from pytest_bdd import given, when, then, parsers, scenarios

from config.paths import feature_path

scenarios(str(feature_path("contact_us_no_upload")))


# ─────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────

@given("I am on the home page")
def open_home_page(home_page, base_url):
    home_page.open_home_page(base_url)


# ─────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────

@when("I open the Contact Us page from the navigation")
def open_contact_us_from_nav(nav_page):
    nav_page.go_to_contact_us()


@when(parsers.parse(
    'I fill in the contact form with name "{name}" email "{email}" '
    'subject "{subject}" and message "{message}"'
))
def fill_contact_form(contact_us_page, name, email, subject, message):
    contact_us_page.fill_contact_form(name, email, subject, message)


@when("I submit the contact form")
def submit_contact_form(contact_us_page):
    contact_us_page.submit_contact_form()


@when("I click the Home button on the Contact Us page")
def click_home_button(contact_us_page):
    contact_us_page.click_home_button()


# ─────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────

@then("the file upload field should not be shown on the Contact Us form")
def assert_upload_field_absent(contact_us_page):
    assert contact_us_page.is_upload_field_absent(), \
        "Expected no file upload field on the Contact Us form"


@then("the name, email, subject and message fields should be shown on the Contact Us form")
def assert_core_fields_shown(contact_us_page):
    assert contact_us_page.are_core_fields_shown(), \
        "Expected the name, email, subject and message fields to be shown"


@then("the Submit button should be shown on the Contact Us form")
def assert_submit_button_shown(contact_us_page):
    assert contact_us_page.is_submit_button_shown(), \
        "Expected the Submit button to be shown on the Contact Us form"


@then("I should see the contact success message")
def assert_success_shown(contact_us_page):
    """Waiting reader: the success banner is expected to appear."""
    assert contact_us_page.has_success_message(), \
        "Expected the contact success message to be shown"


@then("I should be returned to the home page")
def assert_on_home_page(home_page, base_url):
    assert home_page.is_loaded(), "Expected to be returned to the home page"
    current = urlsplit(home_page.page.url)
    expected = urlsplit(base_url)
    assert current.netloc == expected.netloc, \
        f"Expected home host {expected.netloc!r}, got {current.netloc!r}"
    assert current.path.rstrip("/") == expected.path.rstrip("/"), \
        f"Expected home path, got {current.path!r}"
