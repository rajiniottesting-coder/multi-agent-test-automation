"""
ProductDetailPage — the single-product detail screen (/product_details/{id}).

Selectors come from the app inventory (`product_detail`), never from literals
here. Methods are business verbs that name what they act on, per the naming
rule: open_product(), add_to_cart(), view_cart_from_modal() — never a bare
open() or submit() that would collide with a later specific method.

App: https://automationexercise.com
"""
from typing import Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class ProductDetailPage(BasePage):
    """Product detail. Selectors: see `product_detail` in the app inventory.

    Reached by clicking a product's View Product link on the listing (whose
    href already carries the product id), so this page object never invents an
    id. The add-to-cart control here is unique to this product — unlike the
    listing's family of 68 — which is why cart scenarios add from here.
    """

    INVENTORY_PAGE = "product_detail"

    # ── actions ──────────────────────────────────────────────
    def add_to_cart(self) -> None:
        """Click Add to cart for THIS product, opening the add-to-cart modal.

        Confirms it is on this page first: filling/clicking a control that is
        not on screen does not fail fast, it burns the full timeout and then
        blames the locator. Waits for the modal so the caller can immediately
        act on it.
        """
        self.require_own_page()
        self.click(self.sel("add_to_cart_button"))
        self.wait_visible(self.sel("added_modal"))

    def view_cart_from_modal(self) -> None:
        """Click 'View Cart' inside the add-to-cart modal to go to the cart.

        The modal appears only after add_to_cart(). This click LEAVES this
        page, so it does not confirm arrival here — the destination's own page
        object confirms the cart.
        """
        self.wait_visible(self.sel("view_cart_link_in_modal"))
        self.click(self.sel("view_cart_link_in_modal"))

    # ── queries ──────────────────────────────────────────────
    def get_product_name(self) -> str:
        """Return the product name shown in the product information block.

        WAITS for the heading, so call this to assert the detail page for a
        given product has loaded.
        """
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))

    def is_showing_product(self, product_name: str) -> bool:
        """True once the detail page for `product_name` is on screen. WAITS.

        Call this only where the product IS expected to be shown; it waits for
        the name heading and times out if the product never appears.
        """
        self.wait_visible(self.sel("product_name"))
        return product_name in self.get_text(self.sel("product_name"))
