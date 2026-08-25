"""
CartPage — the shopping cart at /view_cart.

Presence checks are by product NAME, scoped to the row that carries the name,
so a row-based assertion never reads the concatenated blob of a whole row.
Deletion is per-row: the delete control is clicked inside the row that
contains the given product name, never on the delete family as a whole.

The cart persists against a signed-in account and survives the run
(persistent_state), so assertions on this page are RELATIVE — that the
product this scenario added is present, or is gone — not absolute counts.

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
    def remove_product(self, product_name: str) -> None:
        """Delete the row for `product_name` by clicking its own delete control.

        Scopes to the row containing the name with click_in_row(), so the
        click lands on the delete control INSIDE that row rather than on the
        delete family as a whole (which would raise a strict-mode violation).
        """
        self.click_in_row(
            self.sel("cart_rows"),
            product_name,
            self.sel("cart_delete_buttons"),
        )
        self.wait_for_row(self.sel("cart_rows"), product_name, present=False)

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the cart table is on screen. WAITS for it.

        Probes the cart table, which is present whether or not the cart holds
        items — a state-independent readiness signal.
        """
        return self.is_showing(self.sel("cart_table"), timeout_ms=timeout_ms)

    def wait_for_product_row(self, product_name: str) -> None:
        """Wait until a cart row containing `product_name` is present.

        WAITS, and times out if the row never appears. Call this only where
        the product IS expected — right after adding it — never to prove
        absence.
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=True)

    def wait_for_product_row_absent(self, product_name: str) -> None:
        """Wait until no cart row contains `product_name`.

        WAITS for the row to disappear, so it is the correct absence check
        after a removal — re-checks until the timeout rather than snapshotting
        the list while it is still settling.
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=False)

    def has_product(self, product_name: str) -> bool:
        """True once a row containing `product_name` is present. WAITS for it.

        Call this only where the product is expected. To assert the product is
        gone, use wait_for_product_row_absent(), which waits for absence — this
        waiting predicate would time out instead of returning False.
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=True)
        return True
