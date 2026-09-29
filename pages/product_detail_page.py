"""
ProductDetailPage — a single product's detail screen (/product_details/{id}).

Selectors come from the `product_detail` page in the app inventory; this file
sets INVENTORY_PAGE and looks each element up with self.sel("<key>"). No literal
selector strings live here.

Method names say WHAT they act on (open_product, add_to_cart) rather than bare
verbs, per the naming rule.

App: https://automationexercise.com
"""
from typing import Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class ProductDetailPage(BasePage):
    """A product's detail page. Selectors: see `product_detail` in the inventory.

    The URL is a TEMPLATE (/product_details/{product_id}), one page per product.
    Prefer reaching it by clicking a product's View Product link on the listing —
    that href already carries the id — so tests never invent a product id.
    """

    INVENTORY_PAGE = "product_detail"

    # ── actions ──────────────────────────────────────────────
    def open_product(self, base_url: str, product_id: str) -> None:
        """Navigate directly to a product's detail page by id.

        Args:
            base_url: application base URL from the `base_url` fixture.
            product_id: the numeric product id used in the URL template.
        """
        self.navigate(f"{base_url.rstrip('/')}{self.page_url(product_id=product_id)}")

    def add_to_cart(self) -> None:
        """Click this product's single Add to cart control.

        Adding opens a MODAL rather than navigating; the modal blocks the page
        underneath. Confirms it is ON this page first — clicking a control that
        is not present would otherwise wait the full timeout and blame the
        selector rather than the wrong page.
        """
        self.require_own_page()
        self.click(self.sel("add_to_cart_button"))

    def view_cart_from_modal(self) -> None:
        """From the add-to-cart modal, click View Cart to go to the cart.

        The modal appears only after add_to_cart(); this proves it appeared and
        navigates to /view_cart.
        """
        self.wait_visible(self.sel("view_cart_link_in_modal"))
        self.click(self.sel("view_cart_link_in_modal"))

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the product detail is on screen. WAITS for it.

        Probes the product name element, which is present in every state this
        page can be in — the readiness signal for 'the detail page loaded'.
        """
        return self.is_showing(self.sel("product_name"), timeout_ms=timeout_ms)

    def product_name(self) -> str:
        """The product's displayed name. WAITS for it to appear."""
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))

    def product_price(self) -> str:
        """The product's displayed price, e.g. 'Rs. 500'. WAITS for it.

        Rendered as 'Rs. <number>'; callers assert on containment of the value.
        """
        self.wait_visible(self.sel("product_price"))
        return self.get_text(self.sel("product_price"))

    def has_added_confirmation(self) -> bool:
        """True once the 'product added to cart' modal is showing. WAITS.

        Call this only where the modal is EXPECTED — it waits up to the timeout
        and would time out rather than return False if the modal never appears.
        """
        return self.is_showing(self.sel("added_modal"))
