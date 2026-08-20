"""
CartPage — the shopping cart screen at /view_cart.

Selectors: see `pages.cart` in the app inventory. Every selector is resolved
through self.sel("<key>"); no literal selectors live in this file.

The cart families (rows, product names, delete buttons) are MULTI-MATCH, so
they are only ever read in bulk (get_all_texts / get_count) or acted on by
scoping to the row that contains a product's name via click_in_row(). Never
click, fill or assert on a family as a whole.

Absolute empty-state assertions are only safe when the scenario owns its
starting state — see the inventory's _starting_state note. This class exposes
both a waiting reader for the empty message and a non-waiting predicate so
callers can assert presence and absence correctly.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class CartPage(BasePage):
    """View Cart. Selectors: see `pages.cart` in the app inventory."""

    INVENTORY_PAGE = "cart"

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the cart table is on screen. WAITS for it."""
        return self.is_showing(self.sel("cart_table"), timeout_ms=timeout_ms)

    def get_product_names(self) -> list[str]:
        """Return every product name currently in the cart, in DOM order."""
        return self.get_all_texts(self.sel("cart_product_names"))

    def get_row_count(self) -> int:
        """Return the number of product rows in the cart."""
        return self.get_count(self.sel("cart_rows"))

    def has_product(self, product_name: str) -> bool:
        """True if a row for the given product name is present in the cart."""
        return any(product_name in name for name in self.get_product_names())

    def has_empty_cart_message(self) -> bool:
        """True if the 'Cart is empty!' message is showing right now.

        Non-waiting probe — the correct reader for asserting the cart is empty,
        since the waiting counterpart would time out when the message is absent.
        """
        return self.is_visible(self.sel("empty_cart_message"))

    def get_empty_cart_message(self) -> str:
        """The 'Cart is empty!' message. WAITS for it to appear.

        Only call this when the cart IS expected to be empty. To assert the
        cart is NOT empty, use has_empty_cart_message(), which does not wait.
        """
        self.wait_visible(self.sel("empty_cart_message"))
        return self.get_text(self.sel("empty_cart_message"))

    # ── actions ──────────────────────────────────────────────
    def remove_product(self, product_name: str) -> None:
        """Delete the row for the given product by scoping to that row.

        Scopes to the row containing the product name and clicks its delete
        control, so the multi-match delete family is never clicked as a whole.
        Removing an item re-renders the table without a page navigation.
        """
        self.click_in_row(
            self.sel("cart_rows"),
            product_name,
            self.sel("cart_delete_buttons"),
        )
