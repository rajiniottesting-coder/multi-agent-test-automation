"""
CartPage — the /view_cart shopping cart.

Selectors: see `pages.cart` in the app inventory. This page carries two mutually
exclusive states: a set of product rows, or the 'Cart is empty!' message when
nothing is in it.

The cart PERSISTS against the signed-in registered account across logout and
across runs (see the inventory's persistent_state_note), so callers must assert
RELATIVELY — that the product THIS test added is present, or is gone — rather
than asserting an absolute count or emptiness, unless the scenario owns its
starting state.

App: https://automationexercise.com
"""
from typing import Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class CartPage(BasePage):
    """The shopping cart at /view_cart.

    Row-scoped reads and delete-by-product actions. Every family key here is
    multi-match (one member per cart row), so members are addressed by the row
    that contains the product name, never by a raw index into the family.
    """

    INVENTORY_PAGE = "cart"

    # ── actions ──────────────────────────────────────────────
    def remove_product(self, product_name: str) -> None:
        """Delete the row for `product_name` by clicking its delete control.

        Scopes to the row containing the product name and clicks the delete
        control inside it, so it never guesses a family index.
        """
        self.require_own_page()
        self.click_in_row(
            self.sel("cart_rows"),
            product_name,
            self.sel("cart_delete_buttons"),
        )

    # ── queries ──────────────────────────────────────────────
    def wait_for_product_present(self, product_name: str) -> None:
        """Wait until a cart row containing `product_name` is present.

        WAITS. Call this right after adding the product; the row may still be
        settling when the browser lands on the cart.
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=True)

    def wait_for_product_absent(self, product_name: str) -> None:
        """Wait until no cart row contains `product_name`.

        WAITS. Call this right after removing the product; reading the list once
        would race the removal and report the row still present.
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=False)

    def get_quantity_for(self, product_name: str) -> str:
        """Return the quantity cell text for `product_name`'s row.

        Addresses the quantity CELL scoped inside the product's row — it does
        not return the whole concatenated row. Returns the cell's text (e.g.
        '1') as a string so the caller can compare it as it sees fit.
        """
        index = self.find_row_index_by_text(self.sel("cart_rows"), product_name)
        assert index >= 0, f"No cart row found for {product_name!r}"
        values = self.get_column_values(
            self.sel("cart_rows"),
            self.sel("cart_quantities"),
            0,
        )
        return values[index]

    def has_product(self, product_name: str) -> bool:
        """True once a row for `product_name` is present. WAITS, and times out
        if it never appears.

        Call this only where presence is the expected answer. A step asking
        'is it there?' to branch on the reply would pay the full timeout every
        time the answer is no. To assert ABSENCE, use wait_for_product_absent()
        instead of negating this.
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=True)
        return True
