"""
CartPage — the shopping cart at /view_cart.

Page object for the cart. Provides row-presence checks scoped by product name
and per-row deletion, plus a relative 'still contains / no longer contains'
pair for scenarios that only own the rows THEY added.

The cart PERSISTS for a registered account across logout and across runs, so a
scenario reusing a shared account inherits leftovers. That is why this page
exposes RELATIVE readers (wait for the row this test added to appear or to
disappear) rather than an absolute empty-cart assertion by default — a
scenario asserting emptiness must own its starting state first.

App: https://automationexercise.com
"""
from typing import List

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class CartPage(BasePage):
    """View Cart. Selectors: see `pages.cart` in the app inventory.

    `cart_rows` is the repeating ROW container — reading its text gives every
    cell of a row concatenated, so never compare it with `==` against a single
    field. Presence checks here scope to the row containing the product name.
    """

    INVENTORY_PAGE = "cart"

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self) -> bool:
        """True once the cart table is on screen. WAITS for it."""
        return self.is_showing(self.sel("cart_table"))

    def get_product_names(self) -> List[str]:
        """Every product name currently in the cart, in DOM order."""
        return self.get_all_texts(self.sel("cart_product_names"))

    def wait_until_contains(self, product_name: str) -> None:
        """Wait until a cart row for `product_name` is present.

        WAITS, and times out if the row never appears. Call this only where
        the product is EXPECTED in the cart — right after adding it.
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=True)

    def wait_until_absent(self, product_name: str) -> None:
        """Wait until no cart row for `product_name` remains.

        WAITS, and times out if the row is still present. Call this only after
        removing the product — asserting a removal that should already have
        happened. This is the relative check: it says nothing about other rows
        the account may already have held.
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=False)

    # ── actions ──────────────────────────────────────────────
    def remove_product(self, product_name: str) -> None:
        """Delete the cart row whose product name is `product_name`.

        Scopes to the row containing the name and clicks the delete control
        inside it, so the right row is removed even when the cart holds
        several products.
        """
        self.require_own_page()
        self.click_in_row(
            self.sel("cart_rows"),
            product_name,
            self.sel("cart_delete_buttons"),
        )
