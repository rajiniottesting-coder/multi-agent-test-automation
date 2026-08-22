"""
CartPage — the shopping cart at /view_cart.

Reads the cart rows, deletes a product by name, and reports whether the cart
is empty. Selectors come from `pages.cart` in the app inventory — no literal
selector strings live in this file.

The cart PERSISTS for a registered account across logout and across runs, so
assert emptiness ABSOLUTELY only when the scenario owns its starting state.
Otherwise prefer the relative reader (product present / gone).

App: https://automationexercise.com
"""
from typing import List, Optional

from pages.base_page import BasePage


class CartPage(BasePage):
    """The shopping cart. Selectors: see `pages.cart` in the app inventory."""

    INVENTORY_PAGE = "cart"

    # ── navigation ───────────────────────────────────────────
    def confirm_arrival(self, **params: object) -> None:
        """Confirm the browser reached the cart page; recover if an ad ate the click."""
        super().confirm_arrival(**params)

    # ── actions ──────────────────────────────────────────────
    def delete_product(self, product_name: str) -> None:
        """Remove the row for `product_name` by clicking its delete control.

        Scoped to the row containing the product name rather than indexing
        into the delete-button family, so it acts on exactly the right row.
        Deletion happens in place with no page navigation.
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

    def product_names(self) -> List[str]:
        """Every product name currently in the cart, in DOM order."""
        return self.get_all_texts(self.sel("cart_product_names"))

    def has_product(self, product_name: str) -> bool:
        """True once a row for `product_name` is present. WAITS for it.

        Call this only where the product IS expected. To assert a product is
        GONE, use wait_until_product_removed(), which waits for absence.
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=True)
        return True

    def wait_until_product_removed(self, product_name: str) -> None:
        """Wait until no row for `product_name` remains. WAITS for absence."""
        self.wait_for_row(self.sel("cart_rows"), product_name, present=False)

    def assert_row_count(self, expected: int) -> None:
        """Wait until exactly `expected` product rows are in the cart."""
        self.wait_for_count(self.sel("cart_rows"), expected)

    def row_text_for(self, product_name: str) -> str:
        """Full text of the cart row containing `product_name`.

        Returns the concatenated text of the whole row (name, price, quantity,
        total), so assert containment against it rather than equality.
        """
        return self.row_containing(self.sel("cart_rows"), product_name).inner_text().strip()

    def is_empty(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the cart shows its empty-state message. WAITS, and times
        out if it is not.

        Emptiness is an ABSOLUTE assertion: the message renders only when no
        rows remain. Call this only where an empty cart is the expected answer,
        and only when the scenario owns its starting state — the cart persists
        for a registered account across runs.
        """
        return self.is_showing(self.sel("empty_cart_message"), timeout_ms=timeout_ms)
