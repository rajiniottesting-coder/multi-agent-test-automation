"""
ProductDetailPage — the per-product details screen at /product_details/{id}.

Selectors: see `pages.product_detail` in the app inventory. Every selector is
resolved through self.sel("<key>"); none appear as literals here.

The page carries a single, unique Add to cart control (unlike the listing
page's family of 68), which is why cart scenarios add products from here. Add
to cart opens a MODAL rather than navigating; the modal blocks the page
underneath, so it must be dismissed or followed through before any further
interaction.

App: https://automationexercise.com
"""
from typing import Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class ProductDetailPage(BasePage):
    """Product detail page. Selectors: see `pages.product_detail` in the inventory."""

    INVENTORY_PAGE = "product_detail"

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the product name is on screen. WAITS for it.

        The product name heading is present in every state this page can be in
        (it does not change when the modal opens or a review is written), so it
        is the state-independent readiness signal for the detail page.
        """
        return self.is_showing(self.sel("product_name"), timeout_ms=timeout_ms)

    def product_name(self) -> str:
        """The product's name. WAITS for it to appear."""
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))

    # ── actions ──────────────────────────────────────────────
    def add_to_cart(self) -> None:
        """Click the single Add to cart control for this product.

        Confirms it is on this page first: filling or clicking a control that
        is not there does not fail fast, it burns the full timeout and then
        blames the locator. This page has exactly one add-to-cart control, so
        no scoping is needed.
        """
        self.require_own_page()
        self.click(self.sel("add_to_cart_button"))

    def view_cart_from_modal(self) -> None:
        """From the add-to-cart modal, follow the View Cart link to the cart.

        The modal appears only after add_to_cart(); this both proves it opened
        and navigates away, so it does not confirm arrival on THIS page — the
        cart page object confirms the cart.
        """
        self.wait_visible(self.sel("added_modal"))
        self.click(self.sel("view_cart_link_in_modal"))
