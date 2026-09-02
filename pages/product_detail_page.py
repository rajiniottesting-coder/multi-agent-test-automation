"""
ProductDetailPage — the /product_details/{product_id} screen.

One page per product. Set INVENTORY_PAGE to the inventory key, then look up
every element by its `elements` key with self.sel("<key>"). No literal
selectors live in this file.

Selectors: see `pages.product_detail` in the app inventory.

App: https://automationexercise.com
"""
from typing import Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class ProductDetailPage(BasePage):
    """A single product's detail page.

    Reaching here by clicking a listing's View Product link is preferred over
    inventing a product id: that href already carries the id. The add-to-cart
    control is UNIQUE on this page (unlike the listing's family of 68), so a
    cart scenario should add the product from here.
    """

    INVENTORY_PAGE = "product_detail"

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the product name heading is on screen. WAITS for it.

        The product name is the most state-independent element the page has:
        it is present the moment the detail page renders and it does not get
        replaced by any interaction, unlike the add-to-cart modal.
        """
        return self.is_showing(self.sel("product_name"), timeout_ms=timeout_ms)

    def product_name(self) -> str:
        """The displayed product name. WAITS for it to appear."""
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))

    # ── actions ──────────────────────────────────────────────
    def add_product_to_cart(self) -> None:
        """Click the single Add to cart control for THIS product.

        Confirms it is on this page first: filling or clicking a control that
        is not on screen does not fail fast — Playwright waits the full timeout
        and then blames the locator, which reads like a broken selector when
        the page is simply wrong. Opens the add-to-cart modal.
        """
        self.require_own_page()
        self.click(self.sel("add_to_cart_button"))
        self.wait_visible(self.sel("added_modal"))

    def view_cart_from_modal(self) -> None:
        """Follow the 'View Cart' link inside the add-to-cart modal.

        The modal exists only after add_product_to_cart(), so wait for it
        before clicking through. This navigates AWAY from this page to the
        cart, so it does not confirm arrival on this page.
        """
        self.wait_visible(self.sel("added_modal"))
        self.click(self.sel("view_cart_link_in_modal"))
