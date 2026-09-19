"""
HomePage — the home / landing screen at '/'.

Reached after login and via the Home navigation link. This app serves the
same path ('/') whether signed in or out, so this page object does not
attempt to judge session state — that is NavPage's job (it reads the
Logout / Logged-in-as controls in the shared navigation).

This page object covers the home-specific content only: the site logo and
the newsletter subscription block. The shopping-session feature lands here
after login and uses it as the arrival point; readiness is confirmed via the
always-present site logo.

App: https://automationexercise.com
"""
from typing import Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class HomePage(BasePage):
    """Home / landing page. Selectors: see `pages.home` in the app inventory."""

    INVENTORY_PAGE = "home"

    # ── actions ──────────────────────────────────────────────
    def open_home(self, base_url: str) -> None:
        """Navigate directly to the home page.

        Args:
            base_url: application base URL from the `base_url` fixture. The
                      path comes from the inventory, never duplicated here.
        """
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.confirm_arrival()

    def subscribe_newsletter(self, email: str) -> None:
        """Enter an email into the footer newsletter box and submit it.

        Named for what it acts on (the newsletter) rather than a bare
        `subscribe`: a bare verb says nothing about its subject and collides
        with any subscribe_<something>() added beside it later.

        Confirms it is on this page first: filling a field that is not on
        screen does not fail fast — Playwright waits the full timeout and
        then blames the locator, which reads like a broken selector when the
        page is simply wrong.
        """
        self.require_own_page()
        self.scroll_to_bottom()
        self.fill(self.sel("subscribe_email_input"), email)
        self.click(self.sel("subscribe_button"))

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the home page has rendered. WAITS for it.

        Probes the site logo, which is present on the home page regardless of
        session state (signed in or out), so it holds in every state this
        page can be in.
        """
        return self.is_showing(self.sel("site_logo"), timeout_ms=timeout_ms)

    def get_subscription_success(self) -> str:
        """The newsletter subscription confirmation text. WAITS for it.

        Only call this when success IS expected; to assert no confirmation is
        shown, use has_subscription_success(), which does not wait.
        """
        self.wait_visible(self.sel("subscribe_success"))
        return self.get_text(self.sel("subscribe_success"))

    def has_subscription_success(self) -> bool:
        """True if the subscription confirmation is showing right now.

        Non-waiting counterpart to get_subscription_success(), for asserting
        that NO confirmation is present. Using the waiting reader for that
        would time out instead of returning False.
        """
        return bool(self.get_all_texts(self.sel("subscribe_success")))
