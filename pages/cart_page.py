"""
CartPage — the shopping cart at /view_cart.

Selectors come from the app inventory (`pages.cart`), never as literals here.

The cart PERSISTS for a registered account across logout and across runs, so
absolute assertions ("cart is empty", "exactly N rows") are unsafe unless the
scenario owns its starting state. The shopping-session scenario asserts
RELATIVELY — that the product it added is present, then that the product it
removed is gone — which holds whatever the account started with. Those two
questions are answered here with waiting row probes (wait_for_row), not with
snapshots of the row list.

App: https://automationexercise.com
"""
from typing import Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class CartPage(BasePage):
    """The shopping cart. Selectors: see `pages.cart` in the app inventory."""

    INVENTORY_PAGE = "cart"

    # ── actions ──────────────────────────────────────────────
    def open_cart(self, base_url: str) -> None:
        """Navigate directly to the cart page."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.confirm_arrival()

    def remove_product(self, product_name: str) -> None:
        """Remove the cart row whose product name matches `product_name`.

        Scopes to the row containing the product name and clicks the delete
        control inside it, so the correct row is removed even when several
        products are in the cart.
        """
        self.require_own_page()
        self.click_in_row(
            self.sel("cart_rows"),
            product_name,
            self.sel("cart_delete_buttons"),
        )

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the cart table is on screen. WAITS for it.

        Call this only where a populated cart is expected. An empty cart shows
        the empty-cart message instead of the table, so this would time out
        there — see is_empty() for that case.
        """
        return self.is_showing(self.sel("cart_table"), timeout_ms=timeout_ms)

    def wait_for_product_row(self, product_name: str) -> None:
        """Wait until a cart row for `product_name` is present.

        WAITS, and times out if the row never appears. Call this to assert the
        product the test added IS in the cart, right after navigating from the
        add-to-cart modal, when the cart is still settling.
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=True)

    def wait_for_product_row_removed(self, product_name: str) -> None:
        """Wait until no cart row for `product_name` remains.

        WAITS, and times out if the row is still present. Call this after a
        removal — the page updates in place without a full navigation, so a
        one-shot read of the row list would race the update and still see the
        row.
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=False)

    def has_product_row(self, product_name: str) -> bool:
        """True once a row for `product_name` is present. WAITS for it.

        Assertion helper for presence: it retries until the timeout, so use it
        only where the row is EXPECTED. To assert absence, use
        wait_for_product_row_removed(), which waits for the row to be gone
        rather than returning False after a timeout.
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=True)
        return True

    def is_empty(self) -> bool:
        """True once the 'Cart is empty!' message is showing. WAITS for it.

        Asserts the cart is empty ABSOLUTELY, so only call it where the
        scenario owns its starting state. The shopping-session scenario does
        NOT — it asserts relatively via wait_for_product_row_removed().
        """
        return self.is_showing(self.sel("empty_cart_message"))
