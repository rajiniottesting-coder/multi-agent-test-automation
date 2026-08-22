"""
ProductDetailPage — a single product's detail screen (/product_details/{id}).

Generated for the shopping-session feature. Follows the LoginPage reference
style: selectors come from the app inventory via self.sel(), methods are
business verbs, and every method uses a BasePage helper.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class ProductDetailPage(BasePage):
    """One product's detail page. Selectors: see `pages.product_detail`.

    The add-to-cart control here is UNIQUE (unlike the listing page's family
    of 68), so adding a product from this page is reliable. Clicking it opens
    a MODAL rather than navigating — dismiss or follow it before touching the
    page underneath.
    """

    INVENTORY_PAGE = "product_detail"

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the product name is on screen. WAITS for it.

        The product name is the most state-independent element on this page:
        it is present in every state, whereas the modal and review-success
        elements appear only after specific interactions.
        """
        return self.is_showing(self.sel("product_name"), timeout_ms=timeout_ms)

    def product_name(self) -> str:
        """The product's name as shown in the product-information block.

        WAITS for it to be visible before reading, so it is safe to call
        immediately after arriving on the page.
        """
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))

    def product_price(self) -> str:
        """The product's price, rendered as e.g. 'Rs. 500'. WAITS for it."""
        self.wait_visible(self.sel("product_price"))
        return self.get_text(self.sel("product_price"))

    # ── actions ──────────────────────────────────────────────
    def add_to_cart(self) -> None:
        """Add this product to the cart and wait for the confirmation modal.

        Clicking opens a modal rather than navigating; this method waits for
        that modal so callers can immediately follow or dismiss it.
        """
        self.click(self.sel("add_to_cart_button"))
        self.wait_visible(self.sel("added_modal"))

    def view_cart_from_modal(self) -> None:
        """Follow the 'View Cart' link inside the add-to-cart modal.

        The modal appears only after add_to_cart(); this navigates away from
        the product page to the cart.
        """
        self.click(self.sel("view_cart_link_in_modal"))

    def continue_shopping(self) -> None:
        """Dismiss the add-to-cart modal and stay on this product page.

        Needed before any further interaction with the page underneath,
        because the modal blocks it.
        """
        self.click(self.sel("continue_shopping_button"))
        self.wait_hidden(self.sel("added_modal"))
