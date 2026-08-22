"""
CartPage — the /view_cart shopping-cart screen.

Selectors come from `pages.cart` in the app inventory; this file never contains
a literal selector string. Methods are business verbs (remove_product,
is_empty) and every one delegates to a BasePage helper.

The cart PERSISTS for a registered account across logout and across runs, so a
scenario asserting an ABSOLUTE state (exactly one row, or empty) must own its
starting state. Where that is not possible, prefer the relative readers here
(has_product, wait for a named row) over absolute counts.

App: https://automationexercise.com
"""
from typing import List, Optional

from pages.base_page import BasePage


class CartPage(BasePage):
    """View-cart screen. Selectors: see `pages.cart` in the app inventory.

    The row, name and delete-button keys are all MULTI-MATCH families (one per
    cart line). Read them with the plural readers; to act on one line, scope to
    the row containing its product name with click_in_row().
    """

    INVENTORY_PAGE = "cart"

    # ── actions ──────────────────────────────────────────────
    def remove_product(self, product_name: str) -> None:
        """Delete the cart row for `product_name`.

        Scopes to the row containing the product name and clicks the delete
        control inside it, so the correct line is removed even when several
        products are in the cart. Removal happens in place — there is no
        navigation — so the caller should confirm with wait_for_removed().
        """
        self.click_in_row(
            self.sel("cart_rows"),
            product_name,
            self.sel("cart_delete_buttons"),
        )

    # ── queries ──────────────────────────────────────────────
    def wait_until_present(self, product_name: str) -> None:
        """Wait until a cart row containing `product_name` is rendered.

        WAITS. Call this after adding a product, when its presence is the
        expected outcome; the cart is often still settling right after the
        navigation that reaches it.
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=True)

    def wait_for_removed(self, product_name: str) -> None:
        """Wait until no cart row containing `product_name` remains.

        WAITS for the row to disappear. The correct absence check after a
        removal: reading the name list once races the in-place delete and can
        report the product still present.
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=False)

    def has_product(self, product_name: str) -> bool:
        """True if a cart row for `product_name` is present right now.

        Non-waiting relative reader, safe on a shared/persistent cart: it
        asserts what THIS test added is present without assuming the cart
        started empty.
        """
        return product_name in self.get_product_names()

    def get_product_names(self) -> List[str]:
        """Visible product names of every cart row, in DOM order."""
        return self.get_all_texts(self.sel("cart_product_names"))

    def get_row_count(self) -> int:
        """Number of product rows currently in the cart (no waiting).

        A snapshot — use only to READ a number, not to assert one. To assert an
        exact count after a change, use assert_row_count().
        """
        return self.get_count(self.sel("cart_rows"))

    def assert_row_count(self, expected: int) -> None:
        """Wait until exactly `expected` cart rows are present.

        WAITS and re-checks until the timeout, naming both numbers if it never
        settles — correct for asserting a count right after an add or remove,
        when the page is still updating.
        """
        self.wait_for_count(self.sel("cart_rows"), expected)

    def is_empty(self) -> bool:
        """True once the 'Cart is empty!' message is shown. WAITS, and times
        out if it is not.

        Call this only where an empty cart is the expected answer, and only
        when the scenario OWNS its starting state (fresh account, or the cart
        cleared first) — the cart persists for a registered account, so this
        asserts emptiness ABSOLUTELY. A step asking "is it empty?" to branch on
        the reply would pay the full timeout every time the answer is no.
        """
        return self.is_showing(self.sel("empty_cart_message"))

    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the cart table is on screen. WAITS for it."""
        return self.is_showing(self.sel("cart_table"), timeout_ms=timeout_ms)
