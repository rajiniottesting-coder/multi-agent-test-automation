"""
CartPage — the shopping cart view (/view_cart).

Selectors: see `pages.cart` in the app inventory. No selector literals live
here — every one is resolved through self.sel("<key>") against INVENTORY_PAGE.

Scope for SCRUM-188: verify a named product row is present, remove it, and
confirm it is gone. The cart persists against the signed-in account, so this
page object asserts RELATIVELY — that the row this test added is present, or
is gone — rather than an absolute count or emptiness, which the scenario does
not own its starting state to claim.
"""
from typing import Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class CartPage(BasePage):
    """Shopping cart. Selectors: see `pages.cart` in the app inventory.

    The row families (cart_rows, cart_product_names, cart_delete_buttons,
    cart_quantities) are MULTI-MATCH. Act on one member by scoping to the row
    that contains the product name — never click the family as a whole.
    """

    INVENTORY_PAGE = "cart"

    # ── actions ──────────────────────────────────────────────
    def remove_product(self, product_name: str) -> None:
        """Remove the row for `product_name` by clicking the delete control
        INSIDE that product's row.

        Scopes to the row containing the name rather than indexing across the
        delete-button family, so the correct row is removed even if the two
        families do not run in lockstep.
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

        Probes the cart table, which is present whenever the cart view has
        loaded with items. Emptiness is a separate, opposite state — do not
        rely on this to assert an empty cart.
        """
        return self.is_showing(self.sel("cart_table"), timeout_ms=timeout_ms)

    def has_product(self, product_name: str, timeout_ms: Optional[int] = None) -> bool:
        """True once a row for `product_name` is present. WAITS for it.

        Call this only where the product is EXPECTED in the cart — the moment
        worth checking is right after adding it, when the table is still
        settling. To assert a product is GONE, use wait_product_removed(),
        which waits for absence instead of timing out.
        """
        self.wait_for_row(
            self.sel("cart_rows"),
            product_name,
            present=True,
            timeout_ms=timeout_ms,
        )
        return True

    def wait_product_removed(
        self, product_name: str, timeout_ms: Optional[int] = None
    ) -> None:
        """Wait until the row for `product_name` is gone from the cart.

        The waiting form for ASBENCE: re-checks until the row disappears rather
        than snapshotting the list right after the removal, when it may still
        be rendered. Raises if the row is still present at the timeout.
        """
        self.wait_for_row(
            self.sel("cart_rows"),
            product_name,
            present=False,
            timeout_ms=timeout_ms,
        )

    def get_product_names(self) -> list[str]:
        """Return the visible name of every product currently in the cart."""
        return self.get_all_texts(self.sel("cart_product_names"))
