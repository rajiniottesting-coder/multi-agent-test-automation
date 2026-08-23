"""
CartPage — the /view_cart shopping-cart screen.

Selectors come from the app inventory (`pages.cart`), never from literals here.
Set INVENTORY_PAGE, then use self.sel("<element_key>").

The cart is PERSISTENT state on this app: it is stored against the signed-in
account and survives logout and the run. A scenario asserting an ABSOLUTE state
(exact row count, emptiness) must own its starting state first — that is what
empty_the_cart() is for. A scenario that only removes what it added should
assert RELATIVELY (the product it added is gone).

App: https://automationexercise.com
"""
from typing import List, Optional

from pages.base_page import BasePage


class CartPage(BasePage):
    """Shopping cart. Selectors: see `pages.cart` in the app inventory.

    The row / name / delete-button families all MULTI-MATCH — one entry per
    product in the cart. Read them with the plural helpers; to act on one
    member, scope to the row containing the product name with click_in_row().
    """

    INVENTORY_PAGE = "cart"

    # ── navigation ───────────────────────────────────────────
    def open_cart(self, base_url: str) -> None:
        """Navigate directly to the cart and confirm arrival."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.confirm_arrival()

    # ── actions ──────────────────────────────────────────────
    def remove_product(self, product_name: str) -> None:
        """Delete the row for `product_name` by clicking its X control.

        Scoped to the row that contains the product name so the correct
        delete control is clicked even with several products in the cart.
        No page navigation follows — the table re-renders in place.
        """
        self.click_in_row(
            self.sel("cart_rows"),
            product_name,
            self.sel("cart_delete_buttons"),
        )
        self.wait_for_row(self.sel("cart_rows"), product_name, present=False)

    def empty_the_cart(self) -> None:
        """Remove every entry, leaving the cart genuinely empty.

        Bind this to a Given so an ABSOLUTE assertion (emptiness / exact
        count) is honest: the scenario put the state there itself. The list
        re-renders after each removal, so re-read the product names each pass
        rather than iterating a stale snapshot.
        """
        while self.get_count(self.sel("cart_rows")) > 0:
            names = self.product_names()
            if not names:
                break
            first = names[0]
            self.click_in_row(
                self.sel("cart_rows"),
                first,
                self.sel("cart_delete_buttons"),
            )
            self.wait_for_row(self.sel("cart_rows"), first, present=False)

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the cart table is on screen. WAITS for it.

        The cart table survives both the populated and (structurally) the
        loaded states, so it is a stable readiness signal.
        """
        return self.is_showing(self.sel("cart_table"), timeout_ms=timeout_ms)

    def product_names(self) -> List[str]:
        """Every product name currently in the cart, in DOM order."""
        return self.get_all_texts(self.sel("cart_product_names"))

    def has_product(self, product_name: str) -> bool:
        """True once a row for `product_name` is present. WAITS for it.

        Call this where PRESENCE is the expected answer. To assert a product
        is GONE, use wait_until_product_removed() — negating this would pay
        the full timeout on every passing run.
        """
        return self.find_row_index_by_text(self.sel("cart_rows"), product_name) != -1

    def wait_until_product_present(self, product_name: str) -> None:
        """Wait until a row for `product_name` appears. Raises on timeout."""
        self.wait_for_row(self.sel("cart_rows"), product_name, present=True)

    def wait_until_product_removed(self, product_name: str) -> None:
        """Wait until no row for `product_name` remains. Raises on timeout."""
        self.wait_for_row(self.sel("cart_rows"), product_name, present=False)

    def is_empty(self) -> bool:
        """True once the cart shows its empty-state message. WAITS, and times
        out if it is not empty.

        Call this only where emptiness is the EXPECTED answer, and only in a
        scenario that owns its starting state (a fresh account or a prior
        empty_the_cart()). A step asking "is it empty?" to branch on the reply
        would pay the full timeout every time the answer is no.
        """
        return self.is_showing(self.sel("empty_cart_message"))

    def row_count(self) -> int:
        """Number of product rows currently rendered (snapshot, no wait).

        For READING a count you are not asserting on. To ASSERT a count after
        an action changed it, use assert_row_count(), which waits.
        """
        return self.get_count(self.sel("cart_rows"))

    def assert_row_count(self, expected: int) -> None:
        """Wait until exactly `expected` product rows are present.

        Safe to assert absolutely here only when the scenario owns its
        starting state — the cart is persistent per account.
        """
        self.wait_for_count(self.sel("cart_rows"), expected)
