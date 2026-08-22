"""
CartPage — the shopping cart at /view_cart.

Selectors come from `pages.cart` in the app inventory; this file declares
INVENTORY_PAGE and looks each element up by key with self.sel(...).

The cart PERSISTS against a signed-in account across logout and across runs,
so absolute-state assertions (exactly one row, cart empty) are only valid
when the scenario owns its starting state. The readers here support both the
absolute waiting form (is_empty, assert_row_count, wait_for_product) and the
relative form (contains_product via wait_for_row).

App: https://automationexercise.com
"""
from typing import List, Optional

from pages.base_page import BasePage


class CartPage(BasePage):
    """Shopping cart. Selectors: see `pages.cart` in the app inventory.

    cart_rows, cart_product_names and cart_delete_buttons are MULTI-MATCH
    families — one member per product row. Never click or assert on them as a
    whole; scope to the row containing the product name with click_in_row(),
    or read the family with the plural helpers.
    """

    INVENTORY_PAGE = "cart"

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the cart table is on screen. WAITS for it.

        The cart table survives both the populated and the just-emptied states
        of the page, so it is the state-independent readiness signal — unlike
        the rows (absent when empty) or the empty-cart message (absent when
        populated).
        """
        return self.is_showing(self.sel("cart_table"), timeout_ms=timeout_ms)

    def product_names(self) -> List[str]:
        """Every product name currently in the cart, in DOM order.

        Read-only snapshot for relative membership assertions. To assert that a
        specific product IS or is GONE, prefer wait_for_product() /
        assert_product_removed(), which re-check until the timeout.
        """
        return self.get_all_texts(self.sel("cart_product_names"))

    def wait_for_product(self, product_name: str) -> None:
        """Wait until a cart row containing `product_name` is present.

        Use after adding a product. Re-checks until the timeout rather than
        reading the list once, because the cart is often still settling right
        after the navigation that landed here.
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=True)

    def assert_product_removed(self, product_name: str) -> None:
        """Wait until no cart row containing `product_name` remains.

        Use after clicking the row's delete control. The waiting form is
        required here: a removal is asynchronous and a snapshot taken
        immediately can still see the row that is on its way out.
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=False)

    def assert_row_count(self, expected: int) -> None:
        """Wait until exactly `expected` product rows are present.

        Uses wait_for_count so the assertion tolerates the page still updating
        after an add or a remove. Only valid when the scenario owns its
        starting cart state.
        """
        self.wait_for_count(self.sel("cart_rows"), expected)

    def is_empty(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the 'Cart is empty!' message is shown. WAITS for it.

        Call this only where an EMPTY cart is the expected answer — it can only
        report False by exhausting its timeout. The message renders solely when
        the cart holds nothing, so asserting on it is an ABSOLUTE emptiness
        claim; the scenario must have owned its starting state.
        """
        return self.is_showing(self.sel("empty_cart_message"), timeout_ms=timeout_ms)

    # ── actions ──────────────────────────────────────────────
    def remove_product(self, product_name: str) -> None:
        """Delete the cart row for `product_name` via its 'X' control.

        Scopes the delete click to the row containing the product name rather
        than indexing into the multi-match delete-button family, so it removes
        the intended product even if row order changes.
        """
        self.click_in_row(
            self.sel("cart_rows"),
            product_name,
            self.sel("cart_delete_buttons"),
        )
