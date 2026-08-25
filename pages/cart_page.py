"""
CartPage — the shopping cart at /view_cart.

Selectors: see `pages.cart` in the app inventory. This page's cart PERSISTS
for a registered account across logout and across runs, so assert RELATIVELY
(this test's product present / gone), never on an absolute row count, unless a
scenario owns its starting state.

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
    def has_row_for(self, product_name: str) -> bool:
        """True once a cart row for `product_name` is present. WAITS.

        Call this only where the row is EXPECTED. To assert a row is ABSENT,
        use wait_until_row_removed(), which waits for it to disappear rather
        than timing out on its absence.
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=True)
        return True

    def wait_until_row_removed(self, product_name: str) -> bool:
        """True once no cart row for `product_name` remains. WAITS for it to go.

        The correct absence assertion here: it re-checks until the row is gone
        rather than reading the list once, which would race the removal that
        triggered it.
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=False)
        return True

    # ── actions ──────────────────────────────────────────────
    def remove_product(self, product_name: str) -> None:
        """Delete the cart row whose description contains `product_name`.

        Scopes the delete control to the row that names the product, rather
        than indexing into the delete-button family — the two families are not
        guaranteed to run in lockstep, so scoping by text is the safe form.
        """
        self.require_own_page()
        self.click_in_row(
            self.sel("cart_rows"),
            product_name,
            self.sel("cart_delete_buttons"),
        )
