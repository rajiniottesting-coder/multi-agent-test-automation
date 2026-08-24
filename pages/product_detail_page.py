"""
ProductDetailPage — a single product's detail screen.

Selectors: see `product_detail` in the app inventory. Every selector is
looked up by key via self.sel(); no literal selector strings live here.

App: https://automationexercise.com
"""
from typing import Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class ProductDetailPage(BasePage):
    """Detail page for one product. Selectors: `product_detail` inventory page.

    The URL is a TEMPLATE (/product_details/{product_id}), so this page is
    normally reached by clicking a product's View Product link on the listing
    rather than navigated to directly.
    """

    INVENTORY_PAGE = "product_detail"

    # ── queries ──────────────────────────────────────────────
    def product_detail_name(self) -> str:
        """The product's name as shown on this detail page. WAITS for it.

        Call this to assert the correct product loaded. Reads the single
        product-information heading, not a family, so equality is safe.
        """
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))

    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the product name heading is on screen. WAITS for it.

        The product name is the most state-independent element on the page:
        it is present in every state (before and after add-to-cart, before
        and after a review), whereas the modal and review-success elements
        exist only after specific interactions.
        """
        return self.is_showing(self.sel("product_name"), timeout_ms=timeout_ms)

    # ── actions ──────────────────────────────────────────────
    def add_product_to_cart(self) -> None:
        """Click Add to cart for THIS product and wait for the modal.

        Confirms it is on this page first: filling/clicking a control that is
        not on screen does not fail fast, so a scenario that skipped a step
        would otherwise burn the full timeout blaming the button selector.
        The add-to-cart control here is unique (unlike the listing's family),
        so a plain click is safe.
        """
        self.require_own_page()
        self.click(self.sel("add_to_cart_button"))
        self.wait_visible(self.sel("added_modal"))

    def view_cart_from_modal(self) -> None:
        """Follow the View Cart link inside the add-to-cart modal.

        Only valid after add_product_to_cart() has opened the modal. Navigates
        to the cart, which also proves the modal appeared.
        """
        self.click(self.sel("view_cart_link_in_modal"))
