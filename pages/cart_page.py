"""
CartPage — the shopping cart (/view_cart).

Selectors come from `pages.cart` in the app inventory; this file never holds a
literal selector. The cart is PERSISTENT state tied to the signed-in account,
so a scenario asserting an absolute count or emptiness must own its starting
state via empty_the_cart() bound to a Given.

App: https://automationexercise.com
"""
from typing import List, Optional

from pages.base_page import BasePage


class CartPage(BasePage):
    """The /view_cart page. Selectors: see `pages.cart` in the app inventory.

    cart_rows, cart_product_names and cart_delete_buttons are MULTI-MATCH
    families — one member per line item. Never click or assert on the family as
    a whole; scope to the row containing the product name, or read the family
    with the plural helpers.
    """

    INVENTORY_PAGE = "cart"

    # ── navigation / actions ─────────────────────────────────
    def open_cart(self, base_url: str) -> None:
        """Navigate directly to the cart page by URL."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    def reload_cart(self) -> None:
        """Full page refresh of the cart, then confirm we are still on it."""
        self.reload()
        self.confirm_arrival()

    def remove_product(self, product_name: str) -> None:
        """Delete the row for `product_name` by clicking its X control.

        Scopes to the row that contains the name rather than indexing across
        the delete-button family, so the correct line item is always removed.
        """
        self.click_in_row(
            self.sel("cart_rows"),
            product_name,
            self.sel("cart_delete_buttons"),
        )
        # After a removal the table re-renders; wait for the row to be gone so
        # a caller reading the cart next does not race the update.
        self.wait_for_row(self.sel("cart_rows"), product_name, present=False)

    def empty_the_cart(self) -> None:
        """Remove every entry, leaving the cart genuinely empty.

        Bind this to a Given so an ABSOLUTE assertion afterwards is honest: the
        scenario put the empty state there itself rather than inheriting it
        from a previous run on the shared account. The list re-renders after
        each removal, so the row set is re-read every iteration.
        """
        while self.get_count(self.sel("cart_rows")) > 0:
            self.click_nth(self.sel("cart_delete_buttons"), 0)
            # Wait for the row count to drop before the next iteration so we do
            # not re-read a stale, still-rendering table.
            self.wait_for_count(
                self.sel("cart_rows"),
                self.get_count(self.sel("cart_rows")) - 1,
            )

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the cart table is on screen. WAITS for it."""
        return self.is_showing(self.sel("cart_table"), timeout_ms=timeout_ms)

    def product_names(self) -> List[str]:
        """Every product name currently in the cart, in order.

        Read from the MULTI-MATCH family with the plural helper — never index
        into it. Use this to assert a product IS present, or to read the whole
        set; use wait_for_product() / assert_row_count() for timing-sensitive
        checks right after an add or remove.
        """
        return self.get_all_texts(self.sel("cart_product_names"))

    def row_count(self) -> int:
        """Number of line-item rows currently rendered (snapshot, no wait).

        For ASSERTING a count use assert_row_count(), which waits; this reader
        is for branching logic that must not pay a timeout.
        """
        return self.get_count(self.sel("cart_rows"))

    def get_quantity_for(self, product_name: str) -> str:
        """The quantity cell text for the row containing `product_name`.

        Reads the whole row's text and is intended for a caller that asserts
        containment; the quantity has no cell-scoped inventory key.
        """
        row = self.row_containing(self.sel("cart_rows"), product_name)
        return (row.inner_text() or "").strip()

    def get_row_text_for(self, product_name: str) -> str:
        """The full concatenated text of the row containing `product_name`.

        A cart row carries name, price, quantity and total together, so assert
        containment (e.g. 'Rs. 1000' in this text), never equality against a
        single field. WAITS for the row to be present.
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=True)
        row = self.row_containing(self.sel("cart_rows"), product_name)
        return (row.inner_text() or "").strip()

    def wait_for_product(self, product_name: str, present: bool = True) -> None:
        """Wait until the row for `product_name` is present, or is gone.

        present=True after an add, present=False after a remove. Re-checks
        until the timeout, which the moment right after the action needs — a
        snapshot read looks once while the table is still settling.
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=present)

    def assert_row_count(self, expected: int) -> None:
        """Wait until exactly `expected` line-item rows are present.

        Uses the waiting counter so a count taken right after an add or remove
        does not read the previous, still-rendering value.
        """
        self.wait_for_count(self.sel("cart_rows"), expected)

    def is_empty(self) -> bool:
        """True once the cart shows its 'Cart is empty!' message. WAITS for it.

        Call this only where emptiness is the EXPECTED answer — it can report
        'no' only by exhausting its timeout. A step branching on whether the
        cart is empty should not use this. Asserting emptiness is absolute, so
        the scenario must own its starting state (see empty_the_cart()).
        """
        return self.is_showing(self.sel("empty_cart_message"))

    def has_empty_message(self) -> bool:
        """True if the empty-cart message is showing right now. Never waits.

        The non-waiting counterpart to is_empty(), for branching logic that
        must not pay a timeout when the cart is NOT empty.
        """
        return self.is_visible(self.sel("empty_cart_message"))
