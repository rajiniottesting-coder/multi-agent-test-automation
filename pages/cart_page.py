"""
CartPage — the /view_cart screen.

Selectors come from `pages.cart` in the app inventory: set INVENTORY_PAGE, then
use self.sel("<key>"). No literal selectors live here.

The cart PERSISTS for a registered account across logout and across runs, so
this account's cart is not guaranteed to be empty. The scenario in this batch
therefore asserts RELATIVELY — that the product this test added is present, and
later that it is gone — rather than asserting an absolute row count. The
waiting readers below (wait_for_row) are built for exactly those relative
presence/absence checks.

App: https://automationexercise.com
"""
from typing import Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class CartPage(BasePage):
    """The shopping cart at /view_cart. Selectors: see `pages.cart`."""

    INVENTORY_PAGE = "cart"

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the cart table is on screen. WAITS for it.

        The cart table is the most state-independent element on this page: it
        is present whenever the cart holds rows, which is the state every
        scenario reaching this page object is in. The inventory declares no
        `readiness` key, so this is the chosen probe.
        """
        return self.is_showing(self.sel("cart_table"), timeout_ms=timeout_ms)

    def contains_product(self, product_name: str) -> None:
        """WAIT until a cart row for `product_name` is present.

        WAITS, and times out if the row never appears. Call this only where the
        product's PRESENCE is the expected answer — for example straight after
        adding it — because it can only report 'no' by exhausting the timeout.
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=True)

    def wait_until_absent(self, product_name: str) -> None:
        """WAIT until no cart row for `product_name` remains.

        The waiting form of an absence check: it re-checks until the row is
        gone or the timeout expires. Use this straight after a removal, when
        the row is expected to disappear but the page may still be settling.
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=False)

    def get_quantity_for(self, product_name: str) -> str:
        """Return the quantity cell text for the row containing `product_name`.

        Scopes the quantity family INSIDE the matching row via the row index,
        so it reads the ONE product's quantity rather than the whole row blob.
        """
        index = self.find_row_index_by_text(self.sel("cart_rows"), product_name)
        assert index >= 0, f"No cart row found for {product_name!r}"
        values = self.get_column_values(
            self.sel("cart_rows"), self.sel("cart_quantities"), index
        )
        return values[index] if index < len(values) else ""

    # ── actions ──────────────────────────────────────────────
    def remove_product(self, product_name: str) -> None:
        """Click the delete control on the row containing `product_name`.

        Scopes to the row rather than indexing a family, so it removes the
        product the test named even if the cart holds other rows.
        """
        self.require_own_page()
        self.click_in_row(
            self.sel("cart_rows"), product_name, self.sel("cart_delete_buttons")
        )
