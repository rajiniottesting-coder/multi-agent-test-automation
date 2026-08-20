"""
CartPage — the /view_cart shopping-cart screen.

Selectors: see `pages.cart` in the app inventory. Every selector is resolved
through self.sel("<key>"); no literal selector strings live in this file.

The cart persists for a registered account across runs, so absolute-state
assertions (like "the cart is empty") are only safe when the scenario owns its
starting state. The methods here support BOTH styles: relative checks (is the
product this test added present?) and, where the caller controls state, the
empty-cart predicate.

The row / name / delete-button families each match one element PER product row,
so they are read with the plural helpers and acted on by scoping to the row
that contains the product name (click_in_row).

App: https://automationexercise.com
"""
from typing import List

from pages.base_page import BasePage


class CartPage(BasePage):
    """Shopping cart. Selectors: see `pages.cart` in the app inventory."""

    INVENTORY_PAGE = "cart"

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self) -> bool:
        """True once the cart table is on screen. WAITS for it."""
        return self.is_showing(self.sel("cart_table"))

    def get_product_names(self) -> List[str]:
        """Visible product names of every row currently in the cart."""
        return self.get_all_texts(self.sel("cart_product_names"))

    def has_product(self, product_name: str) -> bool:
        """True if a row for `product_name` is present in the cart.

        The safe relative assertion: it holds whatever else the account's cart
        started with. Does not wait — call it after the cart page has loaded.
        """
        return any(product_name in name for name in self.get_product_names())

    def get_product_row_count(self) -> int:
        """Number of product rows currently in the cart."""
        return self.get_count(self.sel("cart_rows"))

    def get_product_row_text(self, product_name: str) -> str:
        """Full text of the row containing `product_name` (id, name, price, qty).

        The row family concatenates every column, so callers assert containment
        of the values they care about rather than equality.
        """
        return self.row_containing(self.sel("cart_rows"), product_name).inner_text().strip()

    def is_cart_empty(self) -> bool:
        """True when the cart shows its 'Cart is empty!' indicator.

        Uses the app's own empty-state element rather than counting rows, and
        does not wait — in the empty case there are no rows to wait for. Only
        meaningful when the scenario owns its starting state (see the
        inventory's _starting_state note).
        """
        return self.is_visible(self.sel("empty_cart_message"))

    # ── actions ──────────────────────────────────────────────
    def remove_product(self, product_name: str) -> None:
        """Click the delete control on the row containing `product_name`.

        Removal happens in place with no navigation; the row disappears from
        the table.
        """
        self.click_in_row(
            self.sel("cart_rows"),
            product_name,
            self.sel("cart_delete_buttons"),
        )

    def wait_until_empty(self) -> None:
        """Wait until the cart shows its empty-state indicator.

        Removal is client-side with no page load, so the caller must wait for
        the empty-state element to render before asserting the cart is empty.
        """
        self.wait_visible(self.sel("empty_cart_message"))
