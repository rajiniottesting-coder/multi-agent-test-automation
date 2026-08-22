"""
CartPage — the shopping cart at /view_cart.

Selectors come from the app inventory (`pages.cart`), never from literals here.
The cart PERSISTS against the signed-in account, so absolute assertions
(exact row count, emptiness) are only valid when the scenario owns its
starting state — see the inventory's _starting_state note.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class CartPage(BasePage):
    """The shopping cart. Selectors: see `pages.cart` in the app inventory.

    The cart rows, product names and delete controls are all MULTI-MATCH
    families. Read them with the plural helpers, and act on ONE member by
    scoping to the row that contains the product name — never by clicking the
    family as a whole.
    """

    INVENTORY_PAGE = "cart"

    # ── actions ──────────────────────────────────────────────
    def open_cart(self, base_url: str) -> None:
        """Navigate directly to the cart page."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    def remove_product(self, product_name: str) -> None:
        """Delete the row for `product_name` by clicking its delete control.

        Scopes to the row containing the product name rather than indexing
        into the delete-button family, so the correct row is removed even if
        the families are not in lockstep.
        """
        self.click_in_row(
            self.sel("cart_rows"),
            product_name,
            self.sel("cart_delete_buttons"),
        )

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the cart table is on screen. WAITS for it.

        Probes the cart table, which is present whether the cart holds items
        or is empty, so it survives both states.
        """
        return self.is_showing(self.sel("cart_table"), timeout_ms=timeout_ms)

    def get_product_names(self) -> list[str]:
        """Every product name currently listed in the cart, in DOM order."""
        return self.get_all_texts(self.sel("cart_product_names"))

    def has_product(self, product_name: str, timeout_ms: Optional[int] = None) -> bool:
        """True once a row for `product_name` is present. WAITS for it.

        Call this only where the product is EXPECTED to be present — it waits
        and will time out if the row never appears. To assert removal, use
        wait_until_product_removed().
        """
        self.wait_for_row(
            self.sel("cart_rows"), product_name, present=True, timeout_ms=timeout_ms
        )
        return True

    def wait_until_product_removed(
        self, product_name: str, timeout_ms: Optional[int] = None
    ) -> bool:
        """True once no row for `product_name` remains. WAITS for its removal.

        The waiting form of an absence check: it re-checks until the row is
        gone or the timeout expires. Call this straight after a removal, when
        the cart is still settling.
        """
        self.wait_for_row(
            self.sel("cart_rows"), product_name, present=False, timeout_ms=timeout_ms
        )
        return True

    def is_empty(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the cart shows its 'Cart is empty!' message. WAITS for it.

        This asserts the cart is empty ABSOLUTELY, so the scenario must own its
        starting state (a fresh account, or a cart cleared first). Call this
        only where emptiness is the expected answer — it waits and times out if
        the cart is not empty.
        """
        return self.is_showing(self.sel("empty_cart_message"), timeout_ms=timeout_ms)

    def assert_row_count(self, expected: int) -> None:
        """Wait until exactly `expected` product rows are present."""
        self.wait_for_count(self.sel("cart_rows"), expected)

    def get_row_text(self, product_name: str) -> str:
        """The full text of the row containing `product_name`.

        Returns the concatenated text of the whole row (name, price, quantity,
        total), so assert containment against it rather than equality.
        """
        row = self.row_containing(self.sel("cart_rows"), product_name)
        return row.inner_text().strip()
