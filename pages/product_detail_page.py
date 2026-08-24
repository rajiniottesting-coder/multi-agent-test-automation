"""
ProductDetailPage — a single product's detail screen (/product_details/{id}).

New page object for the shopper-session feature. Style copied from
pages/login_page.py:

  - SELECTORS COME FROM THE APP INVENTORY. Set INVENTORY_PAGE, then look each
    element up with self.sel("<key>"). No literal selectors here.
  - methods are business verbs that say WHAT they act on (open_product,
    add_to_cart, view_cart_from_modal), never a bare open()/click().
  - every method uses a BasePage helper; no raw self.page.* calls.
  - no assertions here — those belong in step definitions.

App: https://automationexercise.com
"""
from typing import Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class ProductDetailPage(BasePage):
    """A product's detail page. Selectors: see `pages.product_detail`.

    The URL is a TEMPLATE (/product_details/{product_id}), one page per
    product. The reliable way here is to click a product's View Product link
    on the listing — that href already carries the id — so this page object
    does not invent ids. The Add to cart control on this page is UNIQUE
    (unlike the listing's family of 68), which is why cart scenarios add from
    here.
    """

    INVENTORY_PAGE = "product_detail"

    # ── actions ──────────────────────────────────────────────
    def open_product(self, base_url: str, product_id: int) -> None:
        """Navigate directly to a product detail page by its id.

        Prefer reaching this page by clicking a product's View Product link on
        the listing, which carries the id already. This direct navigation is
        for the case where the id is known up front.
        """
        self.navigate(f"{base_url.rstrip('/')}{self.page_url(product_id=product_id)}")

    def add_to_cart(self) -> None:
        """Click this product's Add to cart button.

        Opens the add-to-cart MODAL rather than navigating; the modal blocks
        the page underneath. Confirms it is on this page first — filling or
        clicking a control that is not on screen would wait the full timeout
        and then blame the locator rather than the wrong page.
        """
        self.require_own_page()
        self.click(self.sel("add_to_cart_button"))

    def view_cart_from_modal(self) -> None:
        """Click 'View Cart' inside the add-to-cart modal.

        Waits for the modal to appear first — the modal exists only after
        add_to_cart(), and proving it appeared is part of the flow. Navigates
        to the cart.
        """
        self.wait_visible(self.sel("added_modal"))
        self.click(self.sel("view_cart_link_in_modal"))

    def continue_shopping(self) -> None:
        """Dismiss the add-to-cart modal and stay on this product page.

        Needed before any further interaction with the page underneath,
        because the modal blocks it.
        """
        self.wait_visible(self.sel("added_modal"))
        self.click(self.sel("continue_shopping_button"))

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the product name is on screen. WAITS for it.

        The product name is the most state-independent element on this page —
        it is present in every state (before and after the add-to-cart modal,
        before and after a review), unlike the modal or review-success
        elements which appear only after an interaction.
        """
        return self.is_showing(self.sel("product_name"), timeout_ms=timeout_ms)

    def get_product_name(self) -> str:
        """The product's displayed name. WAITS for it to appear.

        Used to confirm the detail page is showing the expected product.
        """
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))

    def is_showing_product(self, product_name: str, timeout_ms: Optional[int] = None) -> bool:
        """True once the detail page shows the given product name. WAITS.

        Call this only where the product IS expected to be on screen; it waits
        up to the timeout and then reports the name it found.
        """
        if not self.is_showing(self.sel("product_name"), timeout_ms=timeout_ms):
            return False
        return product_name in self.get_text(self.sel("product_name"))
