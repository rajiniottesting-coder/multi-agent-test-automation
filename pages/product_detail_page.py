"""
ProductDetailPage — a single product's detail screen (/product_details/{id}).

Selectors: see `product_detail` in the app inventory. No selector literals
live here; every element is resolved with self.sel("<key>").

The add-to-cart flow on this page opens a MODAL rather than navigating, and
the modal blocks the page underneath. Callers that want to keep interacting
with the product must dismiss it (continue_shopping_from_modal); callers that
want the cart go through it (view_cart_from_modal).

App: https://automationexercise.com
"""
from typing import Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class ProductDetailPage(BasePage):
    """One product's detail page. Selectors: `product_detail` in the inventory.

    Reached by clicking a product's View Product link on the listing (its href
    already carries the id), which is why this page object exposes no method
    that invents a product id.
    """

    INVENTORY_PAGE = "product_detail"

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the product detail page is on screen. WAITS for it.

        Probes the product name heading, which is present in every state this
        page can be in (before and after adding to cart), so it is a stable
        readiness signal.
        """
        return self.is_showing(self.sel("product_name"), timeout_ms=timeout_ms)

    def product_name(self) -> str:
        """The displayed product name. WAITS for the heading to appear."""
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))

    # ── actions ──────────────────────────────────────────────
    def add_displayed_product_to_cart(self) -> None:
        """Add THIS product to the cart, opening the add-to-cart modal.

        Confirms it is on this page first: adding from elsewhere would wait the
        full timeout on the button and then blame the selector.
        """
        self.require_own_page()
        self.click(self.sel("add_to_cart_button"))
        self.wait_visible(self.sel("added_modal"))

    def view_cart_from_modal(self) -> None:
        """From the add-to-cart modal, navigate to the cart.

        The modal must be showing (add_displayed_product_to_cart opens it).
        This leaves the page, so it does not confirm arrival here — the cart
        page object confirms its own arrival.
        """
        self.click(self.sel("view_cart_link_in_modal"))

    def continue_shopping_from_modal(self) -> None:
        """Dismiss the add-to-cart modal and stay on this product page.

        Needed before any further interaction with the page underneath, since
        the modal blocks it. Waits for the modal to disappear so a following
        action does not race the overlay.
        """
        self.click(self.sel("continue_shopping_button"))
        self.wait_hidden(self.sel("added_modal"))
