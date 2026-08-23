"""
HomePage — the landing page after login and the site's root ('/').

Selectors come from the app inventory (`pages.home`); this file never contains
a literal selector string. It declares INVENTORY_PAGE and resolves every
element through self.sel("<key>").

The home page carries the site logo and the newsletter subscription block.
This page object exposes readiness and subscription helpers; the top
navigation (Products link, Logout link, "Logged in as") lives on NavPage,
which is where login-recognition assertions belong.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class HomePage(BasePage):
    """The home page landed on after a successful login.

    Selectors: see `pages.home` in the app inventory. Readiness is probed on
    the site logo, which is present in every state of this page (signed in or
    out, subscribed or not), so it is a stable "the home page has loaded"
    signal.
    """

    INVENTORY_PAGE = "home"

    # ── actions ──────────────────────────────────────────────
    def open_home(self, base_url: str) -> None:
        """Navigate directly to the home page.

        Args:
            base_url: application base URL from the `base_url` fixture. The
                      path comes from the inventory, so it is never duplicated
                      here.
        """
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    def subscribe_newsletter(self, email: str) -> None:
        """Enter an email into the newsletter box and submit it."""
        self.fill(self.sel("subscribe_email_input"), email)
        self.click(self.sel("subscribe_button"))

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the home page has loaded. WAITS for the site logo.

        The logo is present in every state of this page, which makes it a
        reliable readiness signal regardless of login state or whether a
        subscription has been submitted.
        """
        return self.is_showing(self.sel("site_logo"), timeout_ms=timeout_ms)

    def is_subscribed(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the subscription success message is shown. WAITS for it.

        Call this only where a successful subscription is the expected answer:
        it waits for the message and times out if it never appears. To branch
        on whether a subscription happened, use has_subscribe_success().
        """
        return self.is_showing(self.sel("subscribe_success"), timeout_ms=timeout_ms)

    def has_subscribe_success(self) -> bool:
        """True if the subscription success message is showing right now.

        Non-waiting counterpart to is_subscribed(), for asserting the message
        is ABSENT without paying a full timeout.
        """
        return bool(self.get_all_texts(self.sel("subscribe_success")))
