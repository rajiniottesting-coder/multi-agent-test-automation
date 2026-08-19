"""
CartPage — the /view_cart shopping cart screen.

Selectors: see `pages.cart` in the app inventory. This page object never
contains literal selector strings; every element is resolved through
self.sel("<key>") against the inventory page keyed by INVENTORY_PAGE.

The cart belongs to the current session/account, so asserting an exact row
count here is safe (unlike the shared catalogue). Exactly one of cart_rows /
empty_cart_message is present at any moment — read presence with the waiting
readers and absence with the non-waiting probes.

App: https://automationexercise.com
"""
from typing import List

from pages.base_page import BasePage


class CartPage(BasePage):
    """Shopping cart. Selectors: see `pages.cart` in the app inventory."""

    INVENTORY_PAGE = "cart"

    # ── navigation ───────────────────────────────────────────
    def open_cart(self, base_url: str) -> None:
        """Navigate directly to the cart page."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    # ── queries ──────────────────────────────────────────────
    def get_product_names(self) -> List[str]:
        """Return the names of every product currently in the cart."""
        return self.get_all_texts(self.sel("cart_product_names"))

    def get_row_count(self) -> int:
        """Return the number of product rows in the cart."""
        return self.get_count(self.sel("cart_rows"))

    def has_product(self, product_name: str) -> bool:
        """True if a row for the given product is present in the cart."""
        return product_name in self.get_product_names()

    def is_empty(self) -> bool:
        """True once the empty-cart message is showing.

        Uses the non-waiting probe so the empty case (no rows to wait for) is
        the expected case and nothing raises. Read absence of rows, not a row
        count, per the inventory: exactly one of cart_rows / empty_cart_message
        is present at any moment.
        """
        return self.is_visible(self.sel("empty_cart_message"))

    # ── actions ──────────────────────────────────────────────
    def remove_product(self, product_name: str) -> None:
        """Delete the row for the named product from the cart.

        Finds the row by its product name and clicks the delete control at the
        matching index — the row family and the delete-button family run in
        lockstep (one delete control per row), so the index is valid in both.
        """
        index = self.find_row_index_by_text(self.sel("cart_rows"), product_name)
        if index < 0:
            raise AssertionError(f"No cart row found for {product_name!r}")
        self.click_nth(self.sel("cart_delete_buttons"), index)
