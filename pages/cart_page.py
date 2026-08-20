"""
CartPage — the shopping cart view (/view_cart).

Reads row counts, product names and prices; deletes a product row by name;
and detects the empty-cart state.

Selectors: see `pages.cart` in the app inventory. This file declares
INVENTORY_PAGE and resolves every selector through self.sel(); no literal
selector strings live here.

App: https://automationexercise.com
"""
from typing import List, Optional

from pages.base_page import BasePage


class CartPage(BasePage):
    """Cart view. Selectors: see `pages.cart` in the app inventory.

    The cart belongs to this test's own session/account, so an EXACT row
    count is a reliable signal here (unlike the shared catalogue). Absolute
    empty-state assertions still require the scenario to own its starting
    state — a fresh session or an emptied cart.
    """

    INVENTORY_PAGE = "cart"

    # ── navigation ───────────────────────────────────────────
    def open_cart(self, base_url: str) -> None:
        """Navigate directly to the cart view."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    def confirm_arrival(self, **params: object) -> None:  # type: ignore[override]
        """Confirm the browser reached the cart page; recover if not."""
        super().confirm_arrival(**params)

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the cart table is on screen. WAITS for it.

        Probes the cart table, which is present whether the cart holds items
        or not, so it is a state-independent readiness signal.
        """
        return self.is_showing(self.sel("cart_table"), timeout_ms=timeout_ms)

    def get_row_count(self) -> int:
        """Number of product rows currently in the cart."""
        return self.get_count(self.sel("cart_rows"))

    def get_product_names(self) -> List[str]:
        """Every product name in the cart, in DOM order.

        Read the family with get_all_texts(); to check that a product IS
        present, assert containment against this list rather than indexing.
        """
        return self.get_all_texts(self.sel("cart_product_names"))

    def has_product(self, product_name: str) -> bool:
        """True if a row for the given product name is present. Never waits."""
        return self.find_row_index_by_text(self.sel("cart_rows"), product_name) != -1

    def get_row_text(self, product_name: str) -> str:
        """Full concatenated text of the row containing the given product.

        Returns id, name, price, quantity and totals together, so assert
        containment (e.g. 'Rs. 500' in row_text) rather than equality.
        """
        row = self.row_containing(self.sel("cart_rows"), product_name)
        return (row.inner_text() or "").strip()

    def is_empty(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the empty-cart message is shown. WAITS for it.

        The empty-cart message is rendered ONLY when the cart holds nothing,
        so use this to assert the cart is empty. To assert the cart is NOT
        empty, count rows instead.
        """
        return self.is_showing(self.sel("empty_cart_message"), timeout_ms=timeout_ms)

    def has_empty_message(self) -> bool:
        """True if the empty-cart message is showing right now. Never waits."""
        return self.is_visible(self.sel("empty_cart_message"))

    # ── actions ──────────────────────────────────────────────
    def remove_product(self, product_name: str) -> None:
        """Delete the row for the given product via its 'X' control.

        Scopes to the row containing the product name, then clicks the delete
        control inside it — never the delete-button family as a whole.
        """
        self.click_in_row(
            self.sel("cart_rows"),
            product_name,
            self.sel("cart_delete_buttons"),
        )
