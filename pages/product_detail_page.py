"""
ProductDetailPage — a single product's detail screen (/product_details/{id}).

New page object for SCRUM-188. Reads the product name and price, and adds the
product to the cart, then dismisses or follows the resulting modal.

Selectors: see `product_detail` in the app inventory. This file holds NO
selector literals — every element is resolved through self.sel("<key>").

App: https://automationexercise.com
"""
from typing import Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class ProductDetailPage(BasePage):
    """One product's detail page. Selectors: `product_detail` in the inventory.

    The URL is a template (one page per product), so this object is normally
    reached by clicking a product's View Product link on the listing — the href
    already carries the product id. open_product() is available when a test
    already knows the id.
    """

    INVENTORY_PAGE = "product_detail"

    # ── actions ──────────────────────────────────────────────
    def open_product(self, base_url: str, product_id: int) -> None:
        """Navigate directly to a product's detail page by id.

        Prefer reaching this page via the listing's View Product link, which
        carries the id already. This is the direct route when a test knows it.
        """
        path = self.page_url(product_id=product_id)
        self.navigate(f"{base_url.rstrip('/')}{path}")
        self.confirm_arrival(product_id=product_id)

    def add_to_cart(self) -> None:
        """Click this product's single Add to cart control.

        Opens the add-to-cart modal rather than navigating. Confirms it is on
        this page first: filling/clicking a control that is not on screen would
        otherwise wait the full timeout and blame the locator.
        """
        self.require_own_page()
        self.click(self.sel("add_to_cart_button"))

    def view_cart_from_modal(self) -> None:
        """Follow the View Cart link inside the add-to-cart modal.

        The modal appears only after add_to_cart(). This also proves the modal
        opened, since the link lives inside it. Navigates to the cart.
        """
        self.wait_visible(self.sel("added_modal"))
        self.click(self.sel("view_cart_link_in_modal"))

    def continue_shopping(self) -> None:
        """Dismiss the add-to-cart modal and stay on this product page.

        Needed before any further interaction with the page underneath, which
        the modal blocks.
        """
        self.wait_visible(self.sel("added_modal"))
        self.click(self.sel("continue_shopping_button"))

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the product name is on screen. WAITS for it.

        No `readiness` key is declared for this page; the product name heading
        is the most state-independent element — it is present whenever the
        detail page has rendered, unlike the modal or review-success text.
        """
        return self.is_showing(self.sel("product_name"), timeout_ms=timeout_ms)

    def product_name(self) -> str:
        """The product's name. WAITS for it to appear."""
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))

    def product_price(self) -> str:
        """The product's price text (rendered as e.g. 'Rs. 500'). WAITS for it."""
        self.wait_visible(self.sel("product_price"))
        return self.get_text(self.sel("product_price"))

    def is_added_modal_shown(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the add-to-cart confirmation modal is showing. WAITS.

        Call this only where the modal is expected. To branch on whether it is
        up, use is_visible on the same element instead — this one times out
        rather than returning False.
        """
        return self.is_showing(self.sel("added_modal"), timeout_ms=timeout_ms)
