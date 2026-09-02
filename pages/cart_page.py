"""
CartPage — the shopping cart screen at /view_cart.

Selectors: see `pages.cart` in the app inventory.

The cart PERSISTS against the signed-in account across logout and across runs
(persistent_state), so this page object exposes only RELATIVE row checks —
"is the product this test added present / gone" — rather than absolute counts.
A scenario that needed an absolute count would have to own its starting state
first, and none in this batch does.

App: https://automationexercise.com
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
        """True once the cart table is on screen. WAITS for it."""
        return self.is_showing(self.sel("cart_table"), timeout_ms=timeout_ms)

    def has_product(self, name: str) -> bool:
        """True once a row for `name` is present. WAITS, and times out if it is not.

        Call this only where the row is EXPECTED to be present. To assert a row
        is ABSENT, use assert_product_absent(), which waits for the row to be
        gone rather than negating this waiting probe.
        """
        self.wait_for_row(self.sel("cart_rows"), name, present=True)
        return True

    def assert_product_absent(self, name: str) -> None:
        """Wait until no cart row contains `name`.

        Uses the waiting-for-absence helper so it re-checks until the removal
        settles, rather than reading the list once immediately after the delete
        click (when the table is still updating) and reporting a stale row.
        """
        self.wait_for_row(self.sel("cart_rows"), name, present=False)

    # ── actions ──────────────────────────────────────────────
    def remove_product(self, name: str) -> None:
        """Click the delete control on the cart row containing `name`.

        Scopes to the row by its product text and clicks the delete control
        inside it, so the per-row delete family is never clicked as a whole.
        """
        self.require_own_page()
        self.click_in_row(
            self.sel("cart_rows"),
            name,
            self.sel("cart_delete_buttons"),
        )
