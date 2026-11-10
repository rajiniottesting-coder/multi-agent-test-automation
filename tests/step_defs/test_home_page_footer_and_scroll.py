"""Step definitions for features/home_page_footer_and_scroll.feature.

Covers the home page footer (newsletter subscription controls) and the
scroll-up arrow behaviour. All UI mechanics are delegated to HomePage; this
module only wires Gherkin phrases to those methods and asserts.
"""
from pytest_bdd import given, when, then, scenarios

from config.paths import feature_path

scenarios(str(feature_path("home_page_footer_and_scroll")))


# ─────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────

@given("I am on the home page")
def open_home_page(home_page, base_url):
    home_page.open_home_page(base_url)


# ─────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────

@when("I scroll down to the footer")
def scroll_to_footer(home_page):
    home_page.scroll_to_footer()


@when("I scroll down partway to the middle of the home page")
def scroll_partway_down(home_page):
    home_page.scroll_partway_down()


@when("I click the scroll-up arrow")
def click_scroll_up_arrow(home_page):
    home_page.scroll_back_to_top()


# ─────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────

@then("the Subscription heading should be shown in the footer")
def assert_subscription_heading(home_page):
    assert home_page.has_subscription_heading(), "Subscription heading not shown in the footer"


@then("the newsletter email input should be shown in the footer")
def assert_subscribe_email_input(home_page):
    assert home_page.has_subscribe_email_input(), "Newsletter email input not shown in the footer"


@then("the subscribe button should be shown in the footer")
def assert_subscribe_button(home_page):
    assert home_page.has_subscribe_button(), "Subscribe button not shown in the footer"


@then("the top of the home page should be displayed")
def assert_at_top(home_page):
    assert home_page.is_at_top(), "Home page is not scrolled to the top"
