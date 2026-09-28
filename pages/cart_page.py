"""
CartPage — the shopping cart at /view_cart.

Selectors come from `pages.cart` in the app inventory; this file uses
self.sel("<key>") and never a literal selector string.

The cart PERSISTS against the signed-in account across logout and across runs
(see the inventory's persistent_state_note). A scenario reusing a shared
account inherits whatever a previous run left behind, so this page object
offers only RELATIVE readers — "is this row present?", "is it gone?" — and no
absolute-count or emptiness assertion, because SCRUM-181 does not own its
starting state.

App: https://automationexercise.com
"""
from typing import Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class CartPage(BasePage):
    """The shopping cart. Selectors: see `pages.cart` in the app inventory.

    `cart_rows` is the repeating row CONTAINER (a multi_match family): reading
    its text gives every cell of a row concatenated, so this class never
    compares it with equality. It scopes to the row containing a product name
    instead, via BasePage row helpers.
    """

    INVENTORY_PAGE = "cart"

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the cart table is on screen. WAITS for it.

        Probes `cart_table`, which is present whether the cart holds rows or is
        empty — a state-independent readiness signal, unlike the row family or
        the empty-cart message, each of which exists in only one state.
        """
        return self.is_showing(self.sel("cart_table"), timeout_ms=timeout_ms)

    def has_product(self, name: str) -> bool:
        """True once a cart row for `name` is present. WAITS for the row.

        Call this only where the product IS expected to be in the cart. It
        answers "no" only by exhausting its timeout, so do not use it to assert
        absence — use is_product_removed() for that, which does not wait for a
        present row.
        """
        self.wait_for_row(self.sel("cart_rows"), name, present=True)
        return True

    def is_product_removed(self, name: str) -> bool:
        """True once no cart row for `name` remains. WAITS for the row to go.

        The counterpart to has_product(), for asserting RELATIVE absence right
        after a removal — it re-checks until the row is gone rather than taking
        a single snapshot while the page is still settling. Other rows the
        account may already hold are not evaluated.
        """
        self.wait_for_row(self.sel("cart_rows"), name, present=False)
        return True

    # ── actions ──────────────────────────────────────────────
    def remove_product(self, name: str) -> None:
        """Remove the cart row for `name` by clicking its delete control.

        Scopes to the row CONTAINING the product name and clicks the delete
        control inside it, rather than indexing across the row and delete
        families — the two need not run in lockstep, and click_in_row keeps the
        selection unambiguous.
        """
        self.require_own_page()
        self.click_in_row(
            self.sel("cart_rows"),
            name,
            self.sel("cart_delete_buttons"),
        )
