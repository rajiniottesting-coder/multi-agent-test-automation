"""
CartPage — the /view_cart shopping cart screen.

Inspect rows for a specific product (name, price, quantity) and remove a
product row. Selectors: see `pages.cart` in the app inventory.

The cart PERSISTS for a registered account across logout and across runs, so
this page's readers assert RELATIVELY — that the product this test added is
present or gone — rather than asserting an absolute count or emptiness on a
shared account.

App: https://automationexercise.com
"""
from typing import Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class CartPage(BasePage):
    """The shopping cart. Selectors: see `pages.cart` in the app inventory.

    Row family is `cart_rows`; the per-column families (`cart_product_names`,
    `cart_quantities`, `cart_delete_buttons`) are scoped INSIDE a row via the
    BasePage row helpers, never acted on as a whole.
    """

    INVENTORY_PAGE = "cart"

    # ── readiness ────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the cart table is on screen. WAITS for it.

        Probes the cart table, which is present whether or not the cart holds
        items — a state-independent readiness signal.
        """
        return self.is_showing(self.sel("cart_table"), timeout_ms=timeout_ms)

    # ── queries ──────────────────────────────────────────────
    def has_product(self, product_name: str) -> bool:
        """True once a row for `product_name` is present. WAITS for it.

        Call this only where presence is the expected answer — it waits up to
        the timeout and returns False only by timing out. To assert ABSENCE,
        use wait_removed(), which waits for the row to disappear.
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=True)
        return True

    def wait_removed(self, product_name: str) -> None:
        """Wait until no row for `product_name` remains in the cart.

        The waiting form of an absence check: re-checks until the row is gone
        or the timeout expires. Use after removing the product.
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=False)

    def quantity_for(self, product_name: str) -> int:
        """Return the quantity shown on the row for `product_name`.

        Scopes the quantity cell INSIDE the matching row, so the value is that
        product's quantity rather than the whole row's concatenated text.
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=True)
        index = self.find_row_index_by_text(self.sel("cart_rows"), product_name)
        text = self.get_column_values(
            self.sel("cart_rows"), self.sel("cart_quantities"), index
        )
        return int(text.strip())

    # ── actions ──────────────────────────────────────────────
    def remove_product(self, product_name: str) -> None:
        """Click the delete control on the row for `product_name`.

        Scopes the click to the row containing the product name so the correct
        row is removed even when the cart holds other items.
        """
        self.require_own_page()
        self.wait_for_row(self.sel("cart_rows"), product_name, present=True)
        self.click_in_row(
            self.sel("cart_rows"), product_name, self.sel("cart_delete_buttons")
        )
