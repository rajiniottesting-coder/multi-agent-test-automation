"""
CartPage — the shopping cart at /view_cart.

Selectors come from `pages.cart` in the app inventory; this file holds no
literal selector strings. Read-only families (rows, names, delete controls)
are queried with plural BasePage helpers, and a single row is removed by
finding its index via its product name and clicking the matching delete
control by position.

App: https://automationexercise.com
"""
from typing import List

from pages.base_page import BasePage


class CartPage(BasePage):
    """Cart page. Selectors: see `pages.cart` in the app inventory.

    The cart belongs to this test's own session, so asserting an exact row
    count is safe here. Exactly one of cart_rows / empty_cart_message is
    present at any moment — assert on the empty-state text after removing the
    last item, never on a row count of zero.
    """

    INVENTORY_PAGE = "cart"

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self) -> bool:
        """True once the cart table is on screen. WAITS for it."""
        return self.is_showing(self.sel("cart_table"))

    def get_product_names(self) -> List[str]:
        """Return every product name currently in the cart, in DOM order."""
        return self.get_all_texts(self.sel("cart_product_names"))

    def get_row_count(self) -> int:
        """Return the number of product rows in the cart."""
        return self.get_count(self.sel("cart_rows"))

    def has_product(self, name: str) -> bool:
        """True if a row for the given product name is present."""
        return any(name in row_name for row_name in self.get_product_names())

    def is_empty(self) -> bool:
        """True once the 'Cart is empty!' message is showing. WAITS for it.

        Use this to assert the cart is empty after removing the last item —
        the empty-state text is what the app renders for this case, whereas a
        row count of zero would be asserting on absence with a waiting reader.
        """
        return self.is_showing(self.sel("empty_cart_message"))

    # ── actions ──────────────────────────────────────────────
    def remove_product(self, name: str) -> None:
        """Remove the row for the named product by clicking its delete control.

        Locates the row by its product name, then clicks the delete control at
        the same index — the row and delete-control families run in lockstep,
        one control per row. Removal happens in place without a navigation.
        """
        index = self.find_row_index_by_text(self.sel("cart_rows"), name)
        if index < 0:
            raise ValueError(f"No cart row found for product {name!r}")
        self.click_nth(self.sel("cart_delete_buttons"), index)
