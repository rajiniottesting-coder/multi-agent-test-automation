"""
CartPage — the /view_cart shopping-cart screen.

Selectors: see `pages.cart` in the app inventory. This class NEVER holds a
literal selector — set INVENTORY_PAGE and resolve every element via
self.sel("<key>").

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class CartPage(BasePage):
    """The shopping cart at /view_cart.

    The cart is a family of rows. Read the family with the plural helpers,
    and act on ONE row by scoping to the product name inside it — never by
    clicking the row family directly (strict-mode violation).

    The cart PERSISTS against a registered account across logout and across
    runs, so asserting an absolute empty state is only safe when the scenario
    owns its starting state. Prefer wait_for_product_row(..., present=False)
    after a removal to assert the product this test added is gone.
    """

    INVENTORY_PAGE = "cart"

    # ── actions ──────────────────────────────────────────────
    def open_cart(self, base_url: str) -> None:
        """Navigate directly to the cart page."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    def remove_product(self, product_name: str) -> None:
        """Delete the cart row for `product_name`.

        Scopes to the row that contains the product name and clicks the delete
        control inside it, so this stays safe with several rows present.
        Removal happens in place — there is no navigation.
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
        """Every product name currently in the cart, in row order."""
        return self.get_all_texts(self.sel("cart_product_names"))

    def has_product(self, product_name: str) -> bool:
        """True if a row for `product_name` is present right now.

        Never waits — use this to branch on optional state. To ASSERT that a
        row is present or gone after an action, use wait_for_product_row.
        """
        return self.find_row_index_by_text(self.sel("cart_rows"), product_name) != -1

    def wait_for_product_row(self, product_name: str, present: bool = True) -> None:
        """Wait until the row for `product_name` is there, or is gone.

        Use present=True after adding a product, present=False after removing
        one. This re-checks until the timeout, so it does not race the in-place
        cart update.
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=present)

    def get_row_text(self, product_name: str) -> str:
        """The full text of the cart row containing `product_name`.

        The row spans every column — description, price, quantity, total — so
        assert containment (e.g. price and quantity) rather than equality.
        """
        return self.row_containing(self.sel("cart_rows"), product_name).inner_text().strip()

    def assert_row_count(self, expected: int) -> None:
        """Wait until exactly `expected` product rows are present.

        WAITS — safe to call right after an add or remove, when the cart is
        still settling.
        """
        self.wait_for_count(self.sel("cart_rows"), expected)

    def is_empty(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the 'Cart is empty!' message is shown. WAITS for it.

        This asserts the cart is empty ABSOLUTELY, so only use it when the
        scenario owns its starting state (a fresh account, or an explicitly
        cleared cart). To assert only that the product this test added is
        gone, prefer wait_for_product_row(name, present=False).
        """
        return self.is_showing(self.sel("empty_cart_message"), timeout_ms=timeout_ms)
