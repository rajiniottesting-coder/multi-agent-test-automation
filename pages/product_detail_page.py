"""
ProductDetailPage — a single product's detail screen (/product_details/{id}).

Selectors come from `pages.product_detail` in the app inventory; this file
holds none. Methods name what they act on (read the product name, add THIS
product to the cart, leave for the cart via the modal), never a bare verb.

App: https://automationexercise.com
"""
from typing import Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class ProductDetailPage(BasePage):
    """Product detail page. Selectors: see `pages.product_detail` in the inventory.

    The add-to-cart control here is UNIQUE (one product per page), unlike the
    listing page's family of 68, which is why a cart scenario adds a product
    from this page rather than from the listing.
    """

    INVENTORY_PAGE = "product_detail"

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the product detail page has rendered its product name.

        The product name heading is present in every state this page can be in
        (a detail page always names its product), so it is a stable readiness
        signal. WAITS for it.
        """
        return self.is_showing(self.sel("product_name"), timeout_ms=timeout_ms)

    def product_name(self) -> str:
        """The product's name as shown on the detail page. WAITS for it.

        Returns the single heading value, not a row blob — this page shows one
        product, so the heading is exactly the name and nothing else.
        """
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))

    # ── actions ──────────────────────────────────────────────
    def add_product_to_cart(self) -> None:
        """Click Add to cart for THIS product and wait for the modal.

        Confirms it is on this page first: filling/clicking a control that is
        not on screen does not fail fast — Playwright waits the full timeout
        and then blames the locator. Adding opens a MODAL rather than
        navigating, so waiting for that modal proves the click registered.
        """
        self.require_own_page()
        self.click(self.sel("add_to_cart_button"))
        self.wait_visible(self.sel("added_modal"))

    def view_cart_from_modal(self) -> None:
        """Follow the 'View Cart' link inside the add-to-cart modal.

        The modal appears only after add_product_to_cart(); this navigates to
        the cart, so it must be called after the product has been added.
        """
        self.wait_visible(self.sel("view_cart_link_in_modal"))
        self.click(self.sel("view_cart_link_in_modal"))
