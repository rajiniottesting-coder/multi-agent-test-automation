"""
ProductDetailPage — a single product's detail screen (/product_details/{id}).

Selectors come from the app inventory (INVENTORY_PAGE = "product_detail").
Reached by clicking a product's View Product link on the listing, or by
navigating with page_url(product_id=...). This page carries the single,
unique Add to cart control for one product, so a cart scenario should add
the product from here rather than from the listing's family of buttons.
"""
from typing import Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class ProductDetailPage(BasePage):
    """Detail screen for one product. Selectors: see `product_detail` in the
    app inventory."""

    INVENTORY_PAGE = "product_detail"

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the product name is on screen. WAITS for it.

        The product name is the most state-independent element on this page:
        it is present on every product's detail view and is not replaced by
        any later interaction (adding to cart opens a modal over it rather
        than navigating).
        """
        return self.is_showing(self.sel("product_name"), timeout_ms=timeout_ms)

    def product_name(self) -> str:
        """The product's name as shown in the product information block.

        WAITS for it, so call this only when the detail page is expected.
        """
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))

    def product_price(self) -> str:
        """The product's price text, e.g. 'Rs. 500'. WAITS for it."""
        self.wait_visible(self.sel("product_price"))
        return self.get_text(self.sel("product_price"))

    def has_added_confirmation(self) -> bool:
        """True once the 'added to cart' modal is showing. WAITS for it.

        Call this only where the confirmation is the expected answer: it
        times out and returns False if the modal never appears.
        """
        return self.is_showing(self.sel("added_modal"))

    # ── actions ──────────────────────────────────────────────
    def add_product_to_cart(self) -> None:
        """Add THIS product to the cart, opening the confirmation modal.

        Confirms it is on this page first: adding as an opening move from
        somewhere else would wait the full timeout on the button and then
        blame the locator, which is fine here — the fault is the page.
        """
        self.require_own_page()
        self.click(self.sel("add_to_cart_button"))

    def view_cart_from_confirmation(self) -> None:
        """Click 'View Cart' inside the add-to-cart modal, landing on the cart.

        The modal appears only after add_product_to_cart(), so call this
        immediately after adding. Navigates away from this page, so it does
        not confirm arrival here — the cart page object confirms its own.
        """
        self.click(self.sel("view_cart_link_in_modal"))
