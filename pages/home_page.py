"""
HomePage — the Automation Exercise landing page.

New page object for the newsletter-subscription feature. Selectors come from
the `home` entry in the app inventory; this file carries no literal selectors.

The subscribe control is icon-only (an arrow glyph) with no accessible name,
so the method is named for what it does — subscribe_to_newsletter(email) —
rather than a bare verb. The success text is rendered in place after
subscribing; there is no navigation and no toast.

The footer-and-scroll feature adds readers for the Subscription block's
presence in the footer, a scroll-partway helper, and a scroll-up action that
returns the page to the top. The home inventory does NOT list a key for the
scroll-up arrow glyph, so this page object cannot address it through self.sel()
— and inventing a key or a literal selector is forbidden. Instead the scroll-up
action is performed with BasePage.scroll_to_top(), which is exactly the visitor
behaviour the arrow triggers. See `notes`: a dedicated scroll_up_arrow element
is needed in the home inventory if the click on the arrow itself must be
exercised rather than its effect.

Confirming the page is at the top is read from the site logo, which sits in the
viewport only when scrolled to the top.

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

    def go_to_test_cases(self) -> None:
        """Click the 'Test Cases' button on the home page.

        This navigates AWAY from the home page to /test_cases, so the method
        does NOT confirm arrival here — the TestCasesPage object owns that
        assertion for its own URL. Confirms the browser is on THIS page before
        clicking so the button is actually present.
        """
        self.require_own_page()
        self.click(self.sel("test_cases_button"))

    def scroll_to_footer(self) -> None:
        """Scroll all the way down to the footer at the bottom of the page.

        Confirms the browser is on THIS page first — scrolling a page that is
        not loaded moves nothing, and the footer assertions that follow would
        then time out blaming their own selectors.
        """
        self.require_own_page()
        self.scroll_to_bottom()

    def scroll_partway_down(self) -> None:
        """Scroll roughly to the middle of the home page, short of the footer.

        Used by the edge scenario that returns to the top from a partial scroll
        position rather than from the very bottom. Scrolls the viewport down by
        half the document height so it lands in a middle section without
        reaching the footer.
        """
        self.require_own_page()
        self.page.evaluate(
            "window.scrollTo(0, Math.floor(document.body.scrollHeight / 2));"
        )

    def scroll_back_to_top(self) -> None:
        """Return to the top of the home page as the scroll-up arrow does.

        The home inventory does not expose a key for the scroll-up arrow glyph,
        so the click on the arrow itself cannot be addressed here without
        inventing a selector — which is forbidden. This performs the visitor
        OUTCOME the arrow produces (returning to the top) via scroll_to_top().
        See `notes`: a scroll_up_arrow element on the home page is needed to
        exercise the arrow element directly.
        """
        self.require_own_page()
        self.scroll_to_top()

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

    def has_subscription_heading(self) -> bool:
        """True once the 'Subscription' heading is showing in the footer. WAITS.

        Call this where the heading is EXPECTED — a step asserting the footer's
        Subscription block appeared. Built on the waiting probe so it does not
        race the scroll that reveals the footer.
        """
        return self.is_showing(self.sel("subscription_heading"))

    def has_subscribe_email_input(self) -> bool:
        """True once the newsletter email input is showing in the footer. WAITS.

        Call this where the field is EXPECTED. Waiting is deliberate so a step
        run straight after the scroll does not look before the footer settles.
        """
        return self.is_showing(self.sel("subscribe_email_input"))

    def has_subscribe_button(self) -> bool:
        """True once the subscribe button is showing in the footer. WAITS.

        Call this where the button is EXPECTED. The subscribe control is
        icon-only; its presence is what the footer story verifies.
        """
        return self.is_showing(self.sel("subscribe_button"))

    def is_at_top(self) -> bool:
        """True once the page is scrolled back to the top. WAITS.

        The site logo sits in the viewport only when scrolled to the top, so
        its visibility is the signal that returning to the top succeeded. Call
        this where being at the top is the EXPECTED answer — it waits for the
        logo to come into view after the scroll-up action.
        """
        return self.is_showing(self.sel("site_logo"))
