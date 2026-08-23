"""
CartPage — the shopping cart at /view_cart.

Selectors: see `cart` in the app inventory. This page holds PERSISTENT state
against the signed-in account, so a scenario asserting an absolute state (an
exact row count, or emptiness) must first own that state via empty_the_cart().

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class CartPage(BasePage):
    """The shopping cart. Selectors: see `cart` in the app inventory.

    The cart persists for a registered account across logout and across runs,
    so any absolute assertion (exact count / emptiness) requires the scenario
    to have cleared the cart first with empty_the_cart().
    """

    INVENTORY_PAGE = "cart"

    # ── actions ──────────────────────────────────────────────
    def open_cart(self, base_url: str) -> None:
        """Navigate directly to the cart page."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.confirm_arrival()

    def empty_the_cart(self) -> None:
        """Remove every entry, leaving the cart genuinely empty.

        Bind this to a Given. After it, an ABSOLUTE assertion (emptiness or an
        exact row count) is honest, because the scenario put the state there
        itself. Re-reads the row count after each removal because the table
        re-renders and the delete family shrinks with it.
        """
        while self.get_count(self.sel("cart_rows")) > 0:
            self.click_nth(self.sel("cart_delete_buttons"), 0)
            # wait for the table to shrink before probing again
            remaining = self.get_count(self.sel("cart_rows"))
            self.wait_for_count(self.sel("cart_rows"), max(remaining - 1, 0))

    def remove_product(self, product_name: str) -> None:
        """Delete the row for the named product, then wait for it to vanish."""
        self.click_in_row(
            self.sel("cart_rows"),
            product_name,
            self.sel("cart_delete_buttons"),
        )
        self.wait_for_row(self.sel("cart_rows"), product_name, present=False)

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the cart table is on screen. WAITS for it."""
        return self.is_showing(self.sel("cart_table"), timeout_ms=timeout_ms)

    def has_product(self, product_name: str) -> bool:
        """True once a row for the product is present. WAITS for it.

        Call this where the product IS expected. It waits for the row and
        times out if it never appears, so it is not a branching probe.
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=True)
        return True

    def is_empty(self) -> bool:
        """True once the cart shows its 'Cart is empty!' message. WAITS.

        Call this only where emptiness is the EXPECTED answer: it waits for the
        empty-state message and times out if the cart is not empty, so a step
        asking "is it empty?" to branch on the reply would pay the full timeout
        every time the answer is no.
        """
        return self.is_showing(self.sel("empty_cart_message"))

    def assert_row_count(self, expected: int) -> None:
        """Wait until the cart holds exactly `expected` product rows."""
        self.wait_for_count(self.sel("cart_rows"), expected)

    def get_product_names(self) -> list[str]:
        """Return the visible product names of every cart row."""
        return self.get_all_texts(self.sel("cart_product_names"))
