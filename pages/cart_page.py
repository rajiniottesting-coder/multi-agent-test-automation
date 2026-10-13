"""
CartPage — the shopping cart at /view_cart.

Selectors come from `pages.cart` in the app inventory; this file never
contains a literal selector string. Methods read like business intent:
presence checks for a named product, a per-product quantity read, and
per-row deletion.

This cart PERSISTS against a signed-in account, but the scenarios in this
batch run anonymously (fresh session), so the cart belongs to the test's own
session. Even so, assertions here are written RELATIVELY — "the product this
test added is present / gone" — which holds whatever the cart started with.
Quantity reads scope the quantity cell inside the product's own row, so the
value returned is that product's, not a concatenation of the whole row.

App: https://automationexercise.com
"""
from typing import Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class CartPage(BasePage):
    """Shopping cart. Selectors: see `pages.cart` in the app inventory.

    Row-scoped families (rows, product names, delete buttons, quantities) are
    multi-match by design. They are never acted on as a whole: deletion is
    scoped to the row containing the product name, and the quantity is read
    from that same row's quantity cell.
    """

    INVENTORY_PAGE = "cart"

    # ── actions ──────────────────────────────────────────────
    def open_cart(self, base_url: str) -> None:
        """Navigate directly to the cart page."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.confirm_arrival()

    def remove_product(self, product_name: str) -> None:
        """Delete the row for `product_name` via its own delete control.

        Scopes to the row containing the product name rather than indexing a
        delete-button family, so the correct row is removed even if the rows
        and the delete controls are not in lockstep.
        """
        self.click_in_row(
            self.sel("cart_rows"),
            product_name,
            self.sel("cart_delete_buttons"),
        )

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the cart table is on screen. WAITS for it.

        Probes the cart table, which is present whether or not the cart holds
        items — a state-independent readiness signal, unlike the empty-state
        message or the product rows, each of which exists in only one state.
        """
        return self.is_showing(self.sel("cart_table"), timeout_ms=timeout_ms)

    def wait_for_product(self, product_name: str, present: bool = True) -> None:
        """Wait until a row for `product_name` is there, or is gone.

        Use present=True after adding and present=False after removing. Both
        forms WAIT: the right moment to check is just after the action that
        changed the cart, when the page is still settling.
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=present)

    def has_product(self, product_name: str) -> bool:
        """True once a row for `product_name` is present. WAITS for it.

        Call this only where the product is EXPECTED to be present — it waits
        and times out if it never appears. To assert a product is ABSENT, use
        wait_for_product(product_name, present=False) instead, which waits for
        the row to disappear rather than timing out on absence.
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=True)
        return True

    def quantity_for(self, product_name: str) -> int:
        """Return the quantity shown in `product_name`'s row, as an int.

        Finds the row by its product name, then reads the quantity cell SCOPED
        to that row (the quantity selector is relative to the row container),
        so the value is this product's quantity and not the whole row's text.
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=True)
        index = self.find_row_index_by_text(self.sel("cart_rows"), product_name)
        values = self.get_column_values(
            self.sel("cart_rows"),
            self.sel("cart_quantities"),
            0,
        )
        raw = values[index].strip()
        return int(raw)

    def product_names(self) -> list[str]:
        """Return the names of every product currently in the cart."""
        return self.get_all_texts(self.sel("cart_product_names"))

    # ── queries added for SCRUM-235 (reusable by SCRUM-220/221) ──
    def confirm_product_present(self, product_name: str) -> bool:
        """True once a row for `product_name` is present. WAITS for it.

        A named confirmation that the product this test added reached the cart,
        asserted RELATIVELY so it holds whatever the cart started with. Call
        only where the product is EXPECTED — it waits and times out on absence.
        To assert absence instead, use wait_for_product(product_name,
        present=False), which waits for the row to disappear.
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=True)
        return True
