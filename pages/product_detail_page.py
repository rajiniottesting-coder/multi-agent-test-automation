"""
ProductDetailPage — a single product's detail screen (/product_details/{id}).

New page object for the shopping-session feature. Responsibilities:
  - read the displayed product name
  - add the product to the cart
  - navigate to the cart via the add-to-cart modal, or dismiss it

Selectors come from the `product_detail` page in the app inventory; this file
never carries a literal selector. Method names say WHAT they act on so they do
not collide with later additions.

App: https://automationexercise.com
"""
from typing import Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class ProductDetailPage(BasePage):
    """Product detail page. Selectors: see `product_detail` in the inventory.

    The URL is a TEMPLATE (one page per product), so this page is normally
    reached by clicking a product's View Product link on the listing rather
    than by navigating to a constructed address.
    """

    INVENTORY_PAGE = "product_detail"

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the product name heading is on screen. WAITS for it.

        The name heading is present in every state of this page, so it is a
        stable readiness signal.
        """
        return self.is_showing(self.sel("product_name"), timeout_ms=timeout_ms)

    def product_name(self) -> str:
        """The displayed product name. WAITS for the heading to appear."""
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))

    # ── actions ──────────────────────────────────────────────
    def add_product_to_cart(self) -> None:
        """Click Add to cart for THIS product and wait for the modal.

        Adding opens a blocking modal rather than navigating, so this waits
        for the modal to confirm the add registered before returning.
        """
        self.require_own_page()
        self.click(self.sel("add_to_cart_button"))
        self.wait_visible(self.sel("added_modal"))

    def view_cart_from_modal(self) -> None:
        """Follow the modal's View Cart link to the cart page."""
        self.wait_visible(self.sel("added_modal"))
        self.click(self.sel("view_cart_link_in_modal"))

    def dismiss_added_modal(self) -> None:
        """Close the add-to-cart modal via Continue Shopping and stay here.

        Needed before any further interaction with the page underneath, which
        the modal blocks while it is open.
        """
        self.click(self.sel("continue_shopping_button"))
        self.wait_hidden(self.sel("added_modal"))
