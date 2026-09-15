"""
ProductDetailPage — a single product's detail page.

App: https://automationexercise.com

Selectors: see `product_detail` in the app inventory. This page carries the
unique add-to-cart control for ONE product (unlike the listing page's family
of 68), so a cart scenario adds the product from here. Adding opens a modal
rather than navigating; the modal blocks the page underneath, so a scenario
must leave it via one of the two modal controls before touching anything else.
"""
from typing import Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class ProductDetailPage(BasePage):
    """One product's detail page. Selectors: `product_detail` in the inventory."""

    INVENTORY_PAGE = "product_detail"

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the product detail page is on screen. WAITS for it.

        Probes the product name heading, which is present in every state this
        page can be in (before and after adding to cart, before and after a
        review), unlike the modal or review-success elements.
        """
        return self.is_showing(self.sel("product_name"), timeout_ms=timeout_ms)

    def product_name(self) -> str:
        """Visible product name shown on this detail page. WAITS for it."""
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))

    # ── actions ──────────────────────────────────────────────
    def add_to_cart(self) -> None:
        """Click the single Add to cart control for THIS product.

        Confirms it is on this page first: filling/clicking a control that is
        not on screen does not fail fast, it burns the full timeout and then
        blames the locator.
        """
        self.require_own_page()
        self.click(self.sel("add_to_cart_button"))
        # The add-to-cart modal opens rather than navigating; wait for it so
        # the caller's next step (View Cart / Continue Shopping) has a target.
        self.wait_visible(self.sel("added_modal"))

    def view_cart_from_modal(self) -> None:
        """Click 'View Cart' inside the add-to-cart modal, landing on the cart.

        Requires the modal to be open — call add_to_cart() first.
        """
        self.wait_visible(self.sel("added_modal"))
        self.click(self.sel("view_cart_link_in_modal"))
