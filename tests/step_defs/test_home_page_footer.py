"""Step definitions for features/home_page_footer.feature.

Verifies the newsletter subscription controls in the home page footer:
the Subscription heading, the email field and the subscribe button.

- Declares every step the paired feature uses (steps are module-scoped).
- Calls HomePage methods only; no selectors appear here.
- Presence assertions use the page object's WAITING has_* readers, which
  retry until the control appears rather than racing the scroll/render.
"""
from pytest_bdd import given, then, scenarios

from config.paths import feature_path

scenarios(str(feature_path("home_page_footer")))


# ─────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────

@given("I am on the home page")
def open_home_page(home_page, base_url):
    home_page.open_home_page(base_url)


# ─────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────

@then("I should see the Subscription heading in the footer")
def assert_subscription_heading(home_page):
    assert home_page.has_subscription_heading(), \
        "Expected the Subscription heading in the footer"


@then("I should see the subscription email field in the footer")
def assert_subscription_email_field(home_page):
    assert home_page.has_subscription_email_field(), \
        "Expected the subscription email field in the footer"


@then("I should see the subscribe button in the footer")
def assert_subscribe_button(home_page):
    assert home_page.has_subscribe_button(), \
        "Expected the subscribe button in the footer"
