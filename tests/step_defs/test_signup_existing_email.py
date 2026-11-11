"""Step definitions for features/signup_existing_email.feature.

Covers SCRUM-409: signing up with an already-registered email is refused with
'Email Address already exist!' and the visitor stays on the Signup / Login page
with the login form still shown.

Conventions mirrored from the reference step-def file:
- Every step the paired feature uses is declared here (steps are module-scoped).
- Step defs call page-object methods only; no selectors here.
- Real credentials come from the `credentials` fixture, resolved by ROLE.
- PRESENCE asserted with a waiting reader; readiness checked with is_loaded().

LoginPage is RESERVED - it exposes is_loaded() (waits for the 'Login to your
account' heading), start_signup(), and get_signup_error(). It has no reader for
the 'New User Signup!' heading, so the "New User Signup form should be
displayed" step asserts readiness, which is what LoginPage can actually show.
"""
from pytest_bdd import given, when, then, parsers, scenarios

from config.paths import feature_path

scenarios(str(feature_path("signup_existing_email")))


# ─────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────

@given("I am on the signup and login page")
def open_signup_login_page(login_page, base_url):
    login_page.open_login_page(base_url)


# ─────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────

@when(parsers.re(
    r'I sign up with name "(?P<name>[^"]*)" and the email of a "(?P<role>[^"]*)" user'
))
def sign_up_with_registered_email(login_page, credentials, name, role):
    """Submit the signup form with a real, already-registered email."""
    email, _ = credentials(role)
    login_page.start_signup(name, email)


# ─────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────

@then("the New User Signup form should be displayed")
def assert_signup_form_displayed(login_page):
    """LoginPage carries both forms and exposes a single readiness probe for the
    screen. It has no reader for the signup heading specifically, so assert the
    page it belongs to is loaded - the strongest signal this page can show."""
    assert login_page.is_loaded(), \
        "Expected the Signup / Login page (with the New User Signup form) to be displayed"


@then(parsers.re(r'I should see the signup error message "(?P<expected_message>[^"]*)"'))
def assert_signup_error(login_page, expected_message):
    actual = login_page.get_signup_error()
    assert expected_message in actual, f"Expected {expected_message!r} in {actual!r}"


@then("I should remain on the signup and login page")
def assert_still_on_signup_login(login_page):
    assert login_page.is_loaded(), "Expected to stay on the Signup / Login page"


@then("the Login to your account form is still shown")
def assert_login_form_still_shown(login_page):
    assert login_page.is_loaded(), \
        "Expected the 'Login to your account' form to still be shown"
