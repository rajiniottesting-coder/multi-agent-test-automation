"""Step definitions for features/newsletter_subscription.feature.

Binds the newsletter subscription scenario to the HomePage page object.
Presence is asserted with the waiting reader (get_subscription_success);
page readiness is asserted with is_loaded. No selectors live here — every
UI interaction goes through a HomePage method.
"""
from pytest_bdd import given, when, then, parsers, scenarios

from config.paths import feature_path

scenarios(str(feature_path("newsletter_subscription")))


# ─────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────

@given("I am on the home page")
def open_home_page(home_page, base_url):
    home_page.open_home_page(base_url)


# ─────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────

@when(parsers.parse('I subscribe to the newsletter with the email "{email}"'))
def subscribe_to_newsletter(home_page, email):
    home_page.subscribe_to_newsletter(email)


# ─────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────

@then(parsers.parse('I should see the subscription success message "{message}"'))
def assert_subscription_success(home_page, message):
    actual = home_page.get_subscription_success()
    assert message in actual, f"Expected {message!r} in {actual!r}"


@then("I should remain on the home page")
def assert_still_on_home(home_page):
    assert home_page.is_loaded(), "Expected to stay on the home page"
