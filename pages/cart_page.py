"""
CartPage — the shopping cart at /view_cart.

Selectors come from the `cart` page in the app inventory. This page object
confirms a named product row is present or gone and removes a row by product
name, scoping every action to the row that contains that name rather than
indexing into the multi-match families.

The cart PERSISTS for a registered account across logout and across runs, so
assert RELATIVELY here — that the product this test added is present, or is
gone — rather than asserting an absolute count or emptiness without owning the
starting state.

App: https://automationexercise.com
"""
from typing import Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class CartPage(BasePage):
    """Shopping cart. Selectors: see `cart` in the app inventory.

    cart_rows / cart_product_names / cart_delete_buttons / cart_quantities are
    all MULTI-MATCH families. Never click, fill or assert on them as a whole —
    scope to the row containing the product name.
    """

    INVENTORY_PAGE = "cart"

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the cart table is on screen. WAITS for it."""
        return self.is_showing(self.sel("cart_table"), timeout_ms=timeout_ms)

    def has_product_row(self, name: str) -> bool:
        """True once a row containing `name` is present. WAITS, and times out
        if it never appears.

        Call this only where the row's presence is the expected answer. A step
        asking 'is it there?' to branch on the reply would pay the full timeout
        every time the row is absent — use wait_for_product_row(present=False)
        to assert absence instead.
        """
        self.wait_for_row(self.sel("cart_rows"), name, present=True)
        return True

    def wait_for_product_row(self, name: str, present: bool = True) -> None:
        """Wait until a row containing `name` is present, or is gone.

        present=True after an addition, present=False after a removal. Re-checks
        until the timeout, so it is safe to call immediately after the action
        that changed the cart.
        """
        self.wait_for_row(self.sel("cart_rows"), name, present=present)

    # ── actions ──────────────────────────────────────────────
    def remove_product(self, name: str) -> None:
        """Remove the row containing `name` from the cart.

        Scopes the delete control to the row that holds the product name rather
        than indexing into the delete-button family, so the correct row is
        removed regardless of ordering. Waits for the row to disappear before
        returning.
        """
        self.require_own_page()
        self.click_in_row(
            self.sel("cart_rows"),
            name,
            self.sel("cart_delete_buttons"),
        )
        self.wait_for_row(self.sel("cart_rows"), name, present=False)
