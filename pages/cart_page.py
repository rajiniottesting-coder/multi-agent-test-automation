"""
CartPage — the shopping cart at /view_cart.

Selectors come from the `cart` page in the app inventory. This page has
persistent_state: the cart is stored against the signed-in account and survives
logout and the run, so a shared account may already hold rows this test did not
add. Every assertion here is therefore RELATIVE — the product this scenario
added is present after adding, and gone after removal — never an absolute count.

App: https://automationexercise.com
"""
from typing import Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class CartPage(BasePage):
    """The shopping cart. Selectors: see `cart` in the app inventory.

    The cart shows one row per product; each row concatenates name, price,
    quantity and total, so this page reads and acts on ROWS scoped by the
    product name rather than by index.
    """

    INVENTORY_PAGE = "cart"

    # ── actions ──────────────────────────────────────────────
    def remove_product(self, product_name: str) -> None:
        """Delete the cart row for `product_name` via its 'x' control.

        Scopes to the row containing the product name, so the correct delete
        control is clicked even when other rows are present. The delete family
        is multi-match, so it must never be clicked directly.
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

        The cart_table id survives both the populated and empty states, so it
        is the state-independent readiness signal for this page.
        """
        return self.is_showing(self.sel("cart_table"), timeout_ms=timeout_ms)

    def contains_product(self, product_name: str) -> bool:
        """True once a row for `product_name` is present. WAITS for it.

        Call this only where the row is EXPECTED — it waits for the row to
        appear and times out if it never does. To assert a product is ABSENT,
        use wait_until_product_removed(), which waits for the row to be gone.
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=True)
        return True

    def wait_until_product_removed(self, product_name: str) -> bool:
        """True once no row for `product_name` remains. WAITS for it to go.

        Use this for the absence assertion after a removal — the moment worth
        checking is right after the delete, when the table is still settling,
        so a single snapshot would race the update and report the row still
        present. `present=False` re-checks until the row is gone.
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=False)
        return True
