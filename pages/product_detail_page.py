"""
ProductDetailPage — a single product's detail screen (/product_details/{id}).

Selectors come from the app inventory (`product_detail`), never from a literal
in this file. Business verbs only; every method uses a BasePage helper.

App: https://automationexercise.com
"""
from typing import Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class ProductDetailPage(BasePage):
    """Product detail page. Selectors: see `product_detail` in the inventory.

    Reached by clicking a product's View Product link on the listing, which
    carries the product id in its href — the test never invents an id. The
    add-to-cart control here is unique (unlike the listing's family of 68),
    which is why cart scenarios add the product from this page.
    """

    INVENTORY_PAGE = "product_detail"

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the product name is on screen. WAITS for it.

        The product name is present in every state this page can be in, before
        and after adding to cart, so it is a stable readiness signal.
        """
        return self.is_showing(self.sel("product_name"), timeout_ms=timeout_ms)

    def product_name(self) -> str:
        """The product's displayed name. WAITS for it to appear."""
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))

    def product_price(self) -> str:
        """The product's displayed price, e.g. 'Rs. 500'. WAITS for it."""
        self.wait_visible(self.sel("product_price"))
        return self.get_text(self.sel("product_price"))

    # ── actions ──────────────────────────────────────────────
    def add_to_cart(self) -> None:
        """Click Add to cart, then wait for the confirmation modal to appear.

        The modal blocks the page underneath, so waiting for it here means a
        follow-up action (view cart / continue shopping) has something to act
        on rather than racing the animation.
        """
        self.require_own_page()
        self.click(self.sel("add_to_cart_button"))
        self.wait_visible(self.sel("added_modal"))

    def view_cart_from_modal(self) -> None:
        """From the add-to-cart modal, click View Cart to go to the cart.

        Leaves this page, so it does not confirm arrival here — the cart page
        object is responsible for confirming it landed on the cart.
        """
        self.wait_visible(self.sel("added_modal"))
        self.click(self.sel("view_cart_link_in_modal"))
