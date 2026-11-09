"""
HomePage — the Automation Exercise landing page.

Page object for the home page. Selectors come from the `home` entry in the app
inventory; this file carries no literal selectors.

Two capabilities live here: the newsletter-subscription flow (footer) and the
'Test Cases' button, which navigates away to the Test Cases page. The button
is labelled, so it is addressed by ARIA role+name via the inventory key.

App: https://automationexercise.com
"""
from typing import Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class HomePage(BasePage):
    """Home page. Selectors: see `pages.home` in the app inventory."""

    INVENTORY_PAGE = "home"

    # ── actions ──────────────────────────────────────────────
    def open_home_page(self, base_url: str) -> None:
        """Navigate to the Automation Exercise home page.

        Args:
            base_url: application base URL, supplied by the `base_url` fixture.
                      The path comes from the inventory, so it is never
                      duplicated here.
        """
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    def subscribe_to_newsletter(self, email: str) -> None:
        """Enter an email in the footer Subscription block and submit.

        Confirms the browser is on THIS page first. Filling a field that is not
        on screen does not fail fast — Playwright waits the full timeout and
        then blames the locator, which reads like a broken selector when the
        page is simply wrong.

        The submit button is icon-only with no accessible name, so it is
        addressed by id (its only handle); this is the case where a css id is
        the correct locator.
        """
        self.require_own_page()
        self.scroll_to_bottom()
        self.fill(self.sel("subscribe_email_input"), email)
        self.click(self.sel("subscribe_button"))

    def click_test_cases_button(self) -> None:
        """Click the 'Test Cases' button, landing on the Test Cases page.

        This leaves the home page, so it does NOT confirm arrival here — the
        destination's own page object is responsible for proving it arrived.
        A click is not a guarantee (an ad interstitial can swallow it), but the
        destination page object is not this one, so recovery belongs there.
        """
        self.require_own_page()
        self.click(self.sel("test_cases_button"))

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the home page is on screen. WAITS for it.

        The home inventory declares no explicit readiness key, so this probes
        the site logo — present on every state of the home page and the most
        state-independent element available.
        """
        return self.is_showing(self.sel("site_logo"), timeout_ms=timeout_ms)

    def get_subscription_success(self) -> str:
        """The 'successfully subscribed' confirmation text. WAITS for it.

        Call this only when success IS expected — it waits for the message to
        render in place after subscribing.
        """
        self.wait_visible(self.sel("subscribe_success"))
        return self.get_text(self.sel("subscribe_success"))

    def has_subscription_success(self) -> bool:
        """True once the subscription success message is showing. WAITS.

        Delegates to the waiting probe so a step asserting the confirmation
        appeared does not race the (non-navigating) in-place render. Call this
        only where success is the expected answer.
        """
        return self.is_showing(self.sel("subscribe_success"))
