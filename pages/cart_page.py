"""
CartPage — the shopping cart at /view_cart.

Reads cart rows and product names, deletes a single row scoped to the product
name, and detects the empty-cart state. Selectors come from `pages.cart` in
the app inventory; this file never contains a literal selector string.

App: https://automationexercise.com
"""
from pages.base_page import BasePage


class CartPage(BasePage):
    """Shopping cart. Selectors: see `pages.cart` in the app inventory.

    The cart is private to the test's own session or account, so asserting on
    the presence of a NAMED product is safe. Absolute row counts are only safe
    once the cart has been emptied — the account persists the cart between runs.
    """

    INVENTORY_PAGE = "cart"

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self) -> bool:
        """True once the cart table is on screen. WAITS for it."""
        return self.is_showing(self.sel("cart_table"))

    def get_product_names(self) -> list[str]:
        """Every product name currently in the cart, in DOM order.

        cart_product_names is a MULTI-MATCH family — read it with the plural
        helper rather than clicking or asserting on it as a whole.
        """
        return self.get_all_texts(self.sel("cart_product_names"))

    def has_product(self, product_name: str) -> bool:
        """True if a cart row for `product_name` is present right now."""
        return any(product_name in name for name in self.get_product_names())

    def get_row_text_for(self, product_name: str) -> str:
        """Concatenated text of the row containing `product_name`.

        The row spans every column (description, price, quantity, total), so
        assert containment against this blob rather than equality with a single
        field value.
        """
        return self.row_containing(self.sel("cart_rows"), product_name).inner_text().strip()

    def is_empty(self) -> bool:
        """True once the 'Cart is empty!' message is showing. WAITS for it.

        The empty-cart message and the cart rows are mutually exclusive — this
        is the mirror of has_product(), and the reliable signal to use after
        removing the last item.
        """
        return self.is_showing(self.sel("empty_cart_message"))

    # ── actions ──────────────────────────────────────────────
    def remove_product(self, product_name: str) -> None:
        """Delete the cart row for `product_name`.

        Scopes the delete control to the row containing the product name rather
        than indexing into the MULTI-MATCH delete family, so the correct row is
        removed. This happens in place, without a page navigation.
        """
        self.click_in_row(
            self.sel("cart_rows"),
            product_name,
            self.sel("cart_delete_buttons"),
        )
