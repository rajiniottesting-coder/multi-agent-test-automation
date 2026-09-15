"""
CartPage — the shopping cart (/view_cart).

Selectors come from the app inventory (`cart` page), never from literals.
The cart PERSISTS against a signed-in account, so this page object exposes
RELATIVE row-presence checks (a named row is present / gone) rather than any
method that would encourage an absolute count on shared account state.

App: https://automationexercise.com
"""
from typing import Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class CartPage(BasePage):
    """The shopping cart. Selectors: see `pages.cart` in the app inventory.

    Row membership is asserted RELATIVELY here: `wait_for_row(..., present=...)`
    holds whatever the account's cart started with, which is the only safe
    assertion against shared, persistent cart state.
    """

    INVENTORY_PAGE = "cart"

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the cart table is on screen. WAITS for it.

        Probes the cart table, which is present whenever the cart page has
        loaded with contents. Call only where the cart is expected to hold
        rows; for the empty case use is_empty().
        """
        return self.is_showing(self.sel("cart_table"), timeout_ms=timeout_ms)

    def has_product(self, product_name: str) -> None:
        """Wait until a cart row containing `product_name` is present.

        WAITS, and times out if the row never appears. Call this only where the
        product is EXPECTED in the cart (e.g. straight after adding it), so the
        wait is the point rather than a cost.
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=True)

    def has_no_product(self, product_name: str) -> None:
        """Wait until no cart row contains `product_name`.

        WAITS for the row to disappear — the correct way to assert absence
        after a removal, since a snapshot taken immediately after the delete
        click can still see the row while the table settles.
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=False)

    def get_product_names(self) -> list[str]:
        """Return the visible product names of every cart row, in order."""
        return self.get_all_texts(self.sel("cart_product_names"))

    def is_empty(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the 'Cart is empty!' message is shown. WAITS for it.

        This asserts the cart is empty ABSOLUTELY, so only call it from a
        scenario that owns its starting cart state. For a shared account,
        prefer has_no_product() to check that what this test added is gone.
        """
        return self.is_showing(self.sel("empty_cart_message"), timeout_ms=timeout_ms)

    # ── actions ──────────────────────────────────────────────
    def remove_product(self, product_name: str) -> None:
        """Delete the cart row for `product_name` via its per-row delete control.

        Scopes to the row containing the product name before clicking, so the
        delete is applied to exactly that product and never to another row.
        """
        self.require_own_page()
        self.click_in_row(
            self.sel("cart_rows"),
            product_name,
            self.sel("cart_delete_buttons"),
        )
