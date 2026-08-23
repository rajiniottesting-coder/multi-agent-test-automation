"""
CartPage — the shopping cart at /view_cart.

Selectors come from the app inventory (`pages.cart`), never from literals here.
The cart is PERSISTENT state kept against the signed-in account, so a scenario
that asserts an ABSOLUTE state (a row count, or emptiness) must first own that
state by calling empty_the_cart(). Asserting that a product this test added is
present is safe regardless of starting state.

App: https://automationexercise.com
"""
from typing import List

from pages.base_page import BasePage


class CartPage(BasePage):
    """Shopping cart. Selectors: see `pages.cart` in the app inventory.

    empty_the_cart() is the clearing helper named by the inventory. It is the
    only sanctioned way to establish a known-empty starting state on this
    account, so persistent-state error messages point callers to it.
    """

    INVENTORY_PAGE = "cart"

    # ── actions ──────────────────────────────────────────────
    def open_cart(self, base_url: str) -> None:
        """Navigate directly to the cart page.

        Args:
            base_url: application base URL from the `base_url` fixture. The path
                      comes from the inventory, so it is never duplicated here.
        """
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.confirm_arrival()

    def remove_product(self, product_name: str) -> None:
        """Remove the row for `product_name` and wait for it to disappear.

        Scopes the delete control to the row containing the product name rather
        than indexing into the delete-button family, which is a multi-match.
        """
        self.click_in_row(
            self.sel("cart_rows"),
            product_name,
            self.sel("cart_delete_buttons"),
        )
        self.wait_for_row(self.sel("cart_rows"), product_name, present=False)

    def empty_the_cart(self) -> None:
        """Remove every entry, leaving the cart genuinely empty.

        Bind this to a Given. After it runs, an ABSOLUTE assertion (the cart is
        empty) is honest because the scenario put the state there itself.

        The list re-renders after each removal, so re-read the row count each
        pass rather than caching it or iterating a stale collection.
        """
        while self.get_count(self.sel("cart_rows")) > 0:
            self.click_nth(self.sel("cart_delete_buttons"), 0)
            self.wait_for_count(
                self.sel("cart_rows"),
                self.get_count(self.sel("cart_rows")) - 1,
            )

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self) -> bool:
        """True once the cart table is on screen. WAITS for it.

        The cart table survives whether the cart holds items or is empty, so it
        is a state-independent readiness signal — unlike the empty-cart message,
        which is present in only one of the two states.
        """
        return self.is_showing(self.sel("cart_table"))

    def get_product_names(self) -> List[str]:
        """Every product name currently in the cart, in order."""
        return self.get_all_texts(self.sel("cart_product_names"))

    def has_product(self, product_name: str) -> bool:
        """True once a row for `product_name` is present. WAITS for it.

        Call this only where the product IS expected to be in the cart — it
        waits and times out if the row never appears. To assert a product was
        removed, use wait_for_removed instead.
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=True)
        return True

    def wait_for_removed(self, product_name: str) -> None:
        """Wait until the row for `product_name` is gone. WAITS for its absence.

        The correct waiting form for asserting a removal: it re-checks until the
        row disappears, rather than reading the list once while it is still
        re-rendering.
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=False)

    def is_empty(self) -> bool:
        """True once the cart shows its empty-state message. WAITS, and times
        out if the cart is NOT empty.

        Call this only where emptiness is the expected answer. A step asking
        "is it empty?" to branch on the reply would pay the full timeout every
        time the answer is no. The empty-state message and the cart rows are
        mutually exclusive — exactly one is present at any moment — so its
        appearance is a reliable emptiness signal.
        """
        return self.is_showing(self.sel("empty_cart_message"))

    def assert_row_count(self, expected: int) -> None:
        """Wait until exactly `expected` product rows are present.

        Uses wait_for_count so a removal or addition that is still settling is
        given time to finish rather than reporting the previous count.
        """
        self.wait_for_count(self.sel("cart_rows"), expected)
