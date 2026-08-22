"""
NavPage — the top navigation bar present on every page.

Selectors: see `pages.nav` in the app inventory. This bar lives once in the
inventory rather than being repeated on each page, so it is the single handle
for navigating between the listing and the cart.

Links here are addressed by href, not by role+name: this app's icon markup
pollutes the accessible name (see the inventory notes on `nav`), so href is the
only reliable contract.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class NavPage(BasePage):
    """Top navigation. Selectors: see `pages.nav` in the app inventory."""

    INVENTORY_PAGE = "nav"

    # ── navigation actions ───────────────────────────────────
    def open_products(self) -> None:
        """Click the Products link and confirm the listing page loaded.

        confirm_arrival on the DESTINATION guards against an ad interstitial
        eating the first navigation after a page load.
        """
        from pages.products_page import ProductsPage

        self.click(self.sel("products_link"))
        ProductsPage(self.page).confirm_arrival()

    def open_cart(self) -> None:
        """Click the Cart link and confirm the cart page loaded."""
        from pages.cart_page import CartPage

        self.click(self.sel("cart_link"))
        CartPage(self.page).confirm_arrival()

    # ── session queries ──────────────────────────────────────
    def wait_until_logged_in(self, timeout_ms: Optional[int] = None) -> bool:
        """True once a session exists. WAITS for the Logout link to appear.

        Call this only where being logged in is the expected outcome. To assert
        that NO session exists, use is_logged_in(), which does not wait.
        """
        return self.is_showing(self.sel("logout_link"), timeout_ms=timeout_ms)

    def is_logged_in(self) -> bool:
        """True if the Logout link is present right now. Never waits.

        The non-waiting counterpart to wait_until_logged_in(), for asserting
        that NO session exists — the waiting reader would time out instead of
        returning False.
        """
        return self.is_visible(self.sel("logout_link"))

    def logged_in_name(self) -> str:
        """The 'Logged in as <name>' banner text. WAITS for it to appear."""
        self.wait_visible(self.sel("logged_in_as"))
        return self.get_text(self.sel("logged_in_as"))
