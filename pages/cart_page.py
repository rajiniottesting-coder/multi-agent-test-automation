"""
CartPage — the /view_cart screen.

Selectors come from the `cart` page in the app inventory; this file resolves
every one through self.sel(...) and never carries a literal.

The cart PERSISTS against a signed-in account, so this page object offers only
RELATIVE assertions — that a named product's row is present, or gone. It
deliberately exposes no absolute empty-cart predicate, because the scenarios in
this batch do not own their starting state (see the inventory's
persistent_state_note for the cart).

App: https://automationexercise.com
"""
import logging
from typing import Optional

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class CartPage(BasePage):
    """The shopping cart. Selectors: see `cart` in the app inventory.

    cart_rows is a MULTI-MATCH row family: its text is every cell of a row
    concatenated, so this object never compares it with ==; it waits for a
    named row to be present or absent, and deletes by scoping to the row that
    contains the product name.
    """

    INVENTORY_PAGE = "cart"

    # ── actions ──────────────────────────────────────────────
    def open_cart(self, base_url: str) -> None:
        """Navigate directly to the cart page."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.confirm_arrival()

    def remove_product(self, product_name: str) -> None:
        """Click the delete control on the row for `product_name`.

        Scopes to the row that contains the name rather than indexing a family,
        so the correct row is removed even though the delete controls are a
        multi-match family.
        """
        self.click_in_row(
            self.sel("cart_rows"),
            product_name,
            self.sel("cart_delete_buttons"),
        )

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the cart table is on screen. WAITS for it."""
        return self.is_showing(self.sel("cart_table"), timeout_ms=timeout_ms)

    def has_product_row(self, product_name: str) -> bool:
        """True once a row for `product_name` is present. WAITS for it.

        Call this only where the row is EXPECTED. To assert a product is gone,
        use wait_until_product_removed(), which waits for absence instead.
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=True)
        return True

    def wait_until_product_removed(self, product_name: str) -> bool:
        """True once no row for `product_name` remains. WAITS for its removal.

        The waiting call for absence: it re-checks until the row is gone, which
        is the moment right after a delete when the table is still settling.
        Call this only where absence is the EXPECTED outcome.
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=False)
        return True
