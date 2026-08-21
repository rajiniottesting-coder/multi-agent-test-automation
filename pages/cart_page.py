"""
CartPage — the shopping cart (/view_cart).

Reads cart rows, per-product quantity and price, removes individual rows,
reloads the page, and detects the empty-cart state.

Selectors: see `pages.cart` in the app inventory. Never a literal here.

App: https://automationexercise.com
"""
from typing import List, Optional

from pages.base_page import BasePage


class CartPage(BasePage):
    """The shopping cart. Selectors: see `pages.cart` in the app inventory.

    The cart is server-owned state tied to the session/account, so exact
    row-count assertions are safe ONLY when the scenario starts from a known
    (empty) state. Family keys (rows, names, delete buttons) must be read with
    plural helpers or scoped to a single row — never clicked as a family.
    """

    INVENTORY_PAGE = "cart"

    # ── actions ──────────────────────────────────────────────
    def open_cart(self, base_url: str) -> None:
        """Navigate directly to the cart page."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.confirm_arrival()

    def reload_cart(self) -> None:
        """Full page refresh of the cart, then confirm we are still here."""
        self.reload()
        self.confirm_arrival()

    def remove_product(self, product_name: str) -> None:
        """Remove the row whose description contains `product_name`.

        Scopes the delete control to the row containing the product name so a
        single member of the delete-button family is clicked, avoiding a
        strict-mode violation.
        """
        self.click_in_row(
            self.sel("cart_rows"),
            product_name,
            self.sel("cart_delete_buttons"),
        )

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the cart table is on screen. WAITS for it.

        The table container is present whether the cart holds items or is empty,
        so it is a state-independent readiness signal for this page.
        """
        return self.is_showing(self.sel("cart_table"), timeout_ms=timeout_ms)

    def assert_row_count(self, expected: int) -> None:
        """Wait until exactly `expected` product rows are present.

        Used right after an add or remove, when the page is still updating; a
        waiting count avoids reading the pre-change snapshot.
        """
        self.wait_for_count(self.sel("cart_rows"), expected)

    def product_names(self) -> List[str]:
        """Every product name currently in the cart, in row order."""
        return self.get_all_texts(self.sel("cart_product_names"))

    def contains_product(self, product_name: str) -> bool:
        """True if a row's description contains `product_name`. WAITS for it.

        A relative check that holds whatever the account started with — for
        asserting the product this test added is present.
        """
        return self.is_showing(self.sel("cart_table")) and any(
            product_name in name for name in self.product_names()
        )

    def get_quantity(self, product_name: str) -> str:
        """Quantity text shown on the row containing `product_name`."""
        row = self.row_containing(self.sel("cart_rows"), product_name)
        return row.locator(".cart_quantity").inner_text().strip()

    def get_total_price(self, product_name: str) -> str:
        """Line-total text (e.g. 'Rs. 1000') on the row containing `product_name`."""
        row = self.row_containing(self.sel("cart_rows"), product_name)
        return row.locator(".cart_total_price").inner_text().strip()

    def is_empty(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the 'Cart is empty!' message is shown. WAITS for it.

        Asserting on this asserts the cart is empty ABSOLUTELY, so the scenario
        must own its starting state (fresh session or an explicit clear).
        """
        return self.is_showing(self.sel("empty_cart_message"), timeout_ms=timeout_ms)
