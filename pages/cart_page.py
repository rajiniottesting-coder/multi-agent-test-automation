"""
CartPage — the shopping cart at /view_cart.

Selectors come from `pages.cart` in the app inventory; this file never holds a
literal selector string. Set INVENTORY_PAGE, then look each element up by its
`elements` key with self.sel("<key>").

The cart PERSISTS against the signed-in account across logout and across runs,
so this page object exposes only RELATIVE assertions — that a product the test
added is present, or is gone. It does not assert an absolute count or emptiness,
because no scenario in this batch owns its starting state.

App: https://automationexercise.com
"""
from typing import Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class CartPage(BasePage):
    """The shopping cart. Selectors: see `pages.cart` in the app inventory.

    The row family is `cart_rows`; the per-row delete control is
    `cart_delete_buttons`. Both are multi-match, so acting on ONE member is
    always scoped to the row that contains the product name via BasePage
    helpers — never by clicking the family directly.
    """

    INVENTORY_PAGE = "cart"

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the cart table is on screen. WAITS for it.

        Probes the cart table container, which is present whenever the cart
        page is rendered with items — the readiness signal for a scenario that
        has just added a product and navigated here.
        """
        return self.is_showing(self.sel("cart_table"), timeout_ms=timeout_ms)

    def wait_for_product_row(self, product_name: str) -> None:
        """Wait until a cart row for `product_name` is present.

        WAITS for the row to appear — call this to assert PRESENCE right after
        adding a product, when the cart may still be settling.
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=True)

    def wait_for_product_row_gone(self, product_name: str) -> None:
        """Wait until the cart row for `product_name` is gone.

        The correct absence assertion after a removal: it re-checks until the
        row disappears rather than reading the list once while it is still
        updating. Relative to what this test added, so it holds whatever the
        account started with.
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=False)

    # ── actions ──────────────────────────────────────────────
    def remove_product(self, product_name: str) -> None:
        """Delete the cart row for `product_name`.

        Confirms it is ON the cart page first, then scopes the click to the row
        that contains the product name so the multi-match delete family is
        never clicked as a whole.
        """
        self.require_own_page()
        self.click_in_row(
            self.sel("cart_rows"),
            product_name,
            self.sel("cart_delete_buttons"),
        )
