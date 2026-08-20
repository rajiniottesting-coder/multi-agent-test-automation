"""
CartPage — the shopping cart view (/view_cart).

Reads cart rows, removes a product by matching its name in the row, and
detects the empty-cart state. Selectors live in the app inventory under the
`cart` page key; this file only names them via self.sel(...).

App: https://automationexercise.com
"""
from typing import List, Optional

from pages.base_page import BasePage


class CartPage(BasePage):
    """The shopping cart. Selectors: see `pages.cart` in the app inventory.

    The cart belongs to this session/account, so an exact row count is a
    reliable signal here — unlike the shared catalogue. Exactly one of
    cart_rows / empty_cart_message is present at any moment.
    """

    INVENTORY_PAGE = "cart"

    # ── navigation ───────────────────────────────────────────
    def open_cart(self, base_url: str) -> None:
        """Navigate directly to the cart view."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    # ── actions ──────────────────────────────────────────────
    def remove_product(self, product_name: str) -> None:
        """Delete the row whose description contains `product_name`.

        Scopes to the row containing the product name and clicks the delete
        control inside it, so it never touches the delete-button family as a
        whole (which would raise a strict-mode violation).
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

    def get_row_count(self) -> int:
        """Number of product rows currently in the cart."""
        return self.get_count(self.sel("cart_rows"))

    def get_product_names(self) -> List[str]:
        """Visible names of every product line item, in order."""
        return self.get_all_texts(self.sel("cart_product_names"))

    def has_product(self, product_name: str) -> bool:
        """True if a row's description contains `product_name`."""
        return any(product_name in name for name in self.get_product_names())

    def is_empty(self) -> bool:
        """True if the cart's own empty-state message is showing.

        Non-waiting probe: in the empty case there are no rows to wait for,
        and the empty-cart message is the app's authored signal for this
        state, so it cannot drift apart from the behaviour.
        """
        return self.is_visible(self.sel("empty_cart_message"))
