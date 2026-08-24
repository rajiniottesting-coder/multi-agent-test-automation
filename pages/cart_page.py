"""
CartPage — the shopping cart at /view_cart.

Selectors: see `pages.cart` in the app inventory.

The cart PERSISTS against a registered account across logout and across runs,
so this page object asserts RELATIVELY: that a product the test added is
present, or that it is gone. It never asserts an absolute row count, because a
shared account can carry leftover rows this scenario does not own.
"""
from typing import Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class CartPage(BasePage):
    """Shopping cart. Selectors: see `pages.cart` in the app inventory."""

    INVENTORY_PAGE = "cart"

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the cart table is on screen. WAITS for it.

        Uses the cart table container rather than the empty-state message or a
        row family, either of which is true in only one of the cart's two
        states. The table is present whether the cart holds items or not.
        """
        return self.is_showing(self.sel("cart_table"), timeout_ms=timeout_ms)

    def wait_until_contains(self, product_name: str) -> None:
        """Wait until a cart row for `product_name` is present.

        Presence assertion after an addition. WAITS, because the cart is still
        settling right after the add-to-cart navigation.
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=True)

    def wait_until_not_contains(self, product_name: str) -> None:
        """Wait until no cart row for `product_name` remains.

        Absence assertion after a removal. WAITS for the row to disappear,
        which is the correct waiting form for absence — a snapshot read right
        after the delete click races the DOM update and can report the row
        still present.
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=False)

    # ── actions ──────────────────────────────────────────────
    def remove_product(self, product_name: str) -> None:
        """Delete the cart row whose description contains `product_name`.

        Scopes to the row containing the product name and clicks the delete
        control inside it, rather than indexing into the delete-button family —
        which would risk acting on the wrong row.
        """
        self.require_own_page()
        self.click_in_row(
            self.sel("cart_rows"),
            product_name,
            self.sel("cart_delete_buttons"),
        )
