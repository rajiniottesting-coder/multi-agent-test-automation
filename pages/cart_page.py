"""
CartPage — the shopping cart screen at /view_cart.

Selectors come from `pages.cart` in the app inventory; this file never contains
a literal selector. Methods are business verbs. The cart belongs to the test's
own session, so an exact row count is safe here.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class CartPage(BasePage):
    """Shopping cart. Selectors: see `pages.cart` in the app inventory.

    cart_rows, cart_product_names and cart_delete_buttons are MULTI-MATCH
    families — read them with the plural helpers and act on ONE member by
    scoping to the row that contains the product name via click_in_row().
    """

    INVENTORY_PAGE = "cart"

    # ── actions ──────────────────────────────────────────────
    def open(self, base_url: str) -> None:
        """Navigate directly to the cart page."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    def remove_product(self, product_name: str) -> None:
        """Delete the row whose description contains `product_name`.

        Scopes to the row containing the product name and clicks the delete
        control inside it, so the multi-match delete family is never clicked
        as a whole. This happens in place — no page navigation.
        """
        self.click_in_row(
            self.sel("cart_rows"),
            product_name,
            self.sel("cart_delete_buttons"),
        )

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the cart table is on screen. WAITS for it."""
        return self.is_showing(self.sel("cart_table"), timeout_ms=timeout_ms)

    def get_product_names(self) -> list[str]:
        """Return the names of every product currently in the cart."""
        return self.get_all_texts(self.sel("cart_product_names"))

    def get_row_count(self) -> int:
        """Return the number of product rows in the cart."""
        return self.get_count(self.sel("cart_rows"))

    def has_product(self, product_name: str) -> bool:
        """True if a row's description contains `product_name`."""
        return any(product_name in name for name in self.get_product_names())

    def get_row_text(self, product_name: str) -> str:
        """Return the full text of the row containing `product_name`.

        The row concatenates every column — description, price, quantity,
        total — so callers assert with containment, not equality.
        """
        return self.row_containing(self.sel("cart_rows"), product_name).inner_text().strip()

    def is_empty(self) -> bool:
        """True when the cart holds no product rows.

        Waits briefly for the empty-cart message the app renders in place of
        the rows, then confirms no rows remain. Non-waiting on the row family
        so absence can be asserted without a timeout.
        """
        self.wait_visible(self.sel("empty_cart_message"))
        return self.get_count(self.sel("cart_rows")) == 0

    def has_empty_message(self) -> bool:
        """True if the 'Cart is empty!' message is showing right now.

        Non-waiting probe, for asserting the cart is empty without risking a
        timeout when the message legitimately is not present.
        """
        return self.is_visible(self.sel("empty_cart_message"))
