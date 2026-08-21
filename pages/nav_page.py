"""
NavPage — the top navigation bar shared by every page.

Selectors: see `pages.nav` in the app inventory. The nav lives once here
rather than repeated on each page. Every link is addressed by href (see the
inventory's _href_over_role note) and pinned to the header copy with nth=0.

App: https://automationexercise.com
"""
from pages.base_page import BasePage


class NavPage(BasePage):
    """Top navigation. Selectors: see `pages.nav` in the app inventory."""

    INVENTORY_PAGE = "nav"

    # ── actions ──────────────────────────────────────────────
    def open_cart(self) -> None:
        """Click the top-nav Cart link and confirm the cart page was reached.

        confirm_arrival is called on the CartPage, since it reads the target
        URL from the object it is called on. Imported locally to avoid a
        circular import at module load.
        """
        from pages.cart_page import CartPage

        self.click(self.sel("cart_link"))
        CartPage(self.page).confirm_arrival()

    def reload_current_page(self) -> None:
        """Full browser refresh of whatever page is currently loaded."""
        self.reload()
