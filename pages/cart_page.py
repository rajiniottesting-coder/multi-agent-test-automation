"""
CartPage — the shopping cart at /view_cart.

Selectors come from `pages.cart` in the app inventory; every selector is looked
up with self.sel("<key>"). No literal selector strings live here.

The cart PERSISTS against the signed-in account, so this page object never
asserts an absolute count. It exposes RELATIVE membership helpers — "is there a
row for <product>?" and "wait until that row is gone" — which hold whatever the
account's cart started with.

App: https://automationexercise.com
"""
from typing import Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class CartPage(BasePage):
    """The shopping cart. Selectors: see `pages.cart` in the app inventory."""

    INVENTORY_PAGE = "cart"

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the cart table is on screen. WAITS for it.

        Probes the cart table, which is present whenever the cart page has
        loaded with contents. Call this only where the cart is expected to
        hold rows.
        """
        return self.is_showing(self.sel("cart_table"), timeout_ms=timeout_ms)

    def has_product_row(self, product_name: str) -> bool:
        """True once a row for `product_name` is present. WAITS for it, and
        times out if it never appears.

        Call this only where the row is the expected answer — for example
        straight after adding the product. To assert a row is GONE, use
        wait_until_product_removed() instead, which waits for absence rather
        than paying the full timeout to answer 'no'.
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=True)
        return True

    def wait_until_product_removed(self, product_name: str) -> None:
        """Wait until no row for `product_name` remains in the cart.

        The waiting form of an ABSENCE check: the delete is asynchronous and
        the row lingers for a moment, so a one-shot read taken right after the
        click still sees it. This re-checks until the row is gone.
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=False)

    # ── actions ──────────────────────────────────────────────
    def remove_product(self, product_name: str) -> None:
        """Delete the cart row whose product name is `product_name`.

        Scopes to the row containing the product name and clicks the delete
        control inside it, rather than indexing across the delete-button
        family — which would risk acting on the wrong row.
        """
        self.require_own_page()
        self.click_in_row(
            self.sel("cart_rows"),
            product_name,
            self.sel("cart_delete_buttons"),
        )
