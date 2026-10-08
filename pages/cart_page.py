"""
CartPage — the shopping cart at /view_cart.

New page object. Conventions copied from LoginPage (the reference):
  - SELECTORS COME FROM THE APP INVENTORY, never a literal in this file.
    Declare INVENTORY_PAGE, then use self.sel("<element_key>").
  - methods are business verbs, not UI mechanics
  - every method uses a BasePage helper; no raw self.page.* calls
  - no assertions here — those belong in step definitions

The cart's row families are multi-match: cart_rows, cart_product_names,
cart_delete_buttons and cart_quantities each match several elements. To act
on ONE product's row, scope to the row containing that product's name with
click_in_row(); to check presence/absence, wait on the row family.

NOTE on starting state: the inventory marks this page persistent_state — the
cart is stored against the signed-in account and survives logout and the run.
A scenario reusing a shared account must assert RELATIVELY (that the product
this test added is present, or is gone), which is what this test case does.
These methods therefore wait for a NAMED row rather than an absolute count.

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
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the cart table is on screen. WAITS for it.

        The cart table is the one element present whether the cart holds items
        or not, so it is the state-independent readiness signal for this page.
        """
        return self.is_showing(self.sel("cart_table"), timeout_ms=timeout_ms)

    def has_product(self, product_name: str, timeout_ms: Optional[int] = None) -> bool:
        """True once a cart row for `product_name` is present. WAITS for it.

        Call this only where the product's PRESENCE is the expected answer —
        e.g. straight after adding it. It waits until the timeout and can only
        answer 'no' by running out of time, so it is not for branching.
        """
        try:
            self.wait_for_row(
                self.sel("cart_rows"),
                product_name,
                present=True,
                timeout_ms=timeout_ms,
            )
            return True
        except Exception:
            logger.info("Cart row for %r did not appear", product_name)
            return False

    def wait_until_product_removed(
        self, product_name: str, timeout_ms: Optional[int] = None
    ) -> None:
        """Wait until the cart row for `product_name` is GONE.

        The waiting form of an absence check: re-checks until the row has
        disappeared, which is the moment right after the delete control is
        clicked. Reading the list once would race the removal and still see
        the row. Raises if the row never goes away.
        """
        self.wait_for_row(
            self.sel("cart_rows"),
            product_name,
            present=False,
            timeout_ms=timeout_ms,
        )

    # ── actions ──────────────────────────────────────────────
    def remove_product(self, product_name: str) -> None:
        """Delete the cart row for `product_name`.

        Scopes to the row CONTAINING the product name and clicks the delete
        control inside it, rather than indexing into the delete-button family —
        click_in_row() keeps the row/control pairing honest. Confirms the cart
        is on screen first so a filled-field-style full timeout cannot masquerade
        as a broken selector.
        """
        self.require_own_page()
        self.click_in_row(
            self.sel("cart_rows"),
            product_name,
            self.sel("cart_delete_buttons"),
        )
