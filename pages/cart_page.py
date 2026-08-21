"""
CartPage — the shopping cart screen (/view_cart).

Selectors come from the app inventory (`pages.cart`), never from literals here.
Reads cart rows and prices, removes a product by name, and detects the
empty-cart state.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class CartPage(BasePage):
    """Shopping cart. Selectors: see `pages.cart` in the app inventory.

    The cart PERSISTS for a registered account across logout and runs, so an
    absolute empty-cart assertion is only valid when the scenario owns its
    starting state. The row/name/delete families are MULTI-MATCH: scope to the
    row containing a product's name rather than indexing a family blindly.
    """

    INVENTORY_PAGE = "cart"

    # ── actions ──────────────────────────────────────────────
    def open_cart(self, base_url: str) -> None:
        """Navigate directly to the cart page."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    def remove_product(self, product_name: str) -> None:
        """Delete the row whose description contains `product_name`.

        Scopes to the row containing the product name before clicking its
        delete control — the delete control is a MULTI-MATCH family, so a bare
        click would raise a strict-mode violation.
        """
        self.click_in_row(
            self.sel("cart_rows"),
            product_name,
            self.sel("cart_delete_buttons"),
        )
        self.wait_for_row(self.sel("cart_rows"), product_name, present=False)

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the cart table is on screen. WAITS for it."""
        return self.is_showing(self.sel("cart_table"), timeout_ms=timeout_ms)

    def get_product_names(self) -> list[str]:
        """Return the description text of every row currently in the cart."""
        return self.get_all_texts(self.sel("cart_product_names"))

    def has_product(self, product_name: str) -> bool:
        """True once a row containing `product_name` is present. WAITS for it.

        Built on wait_for_row so an assertion made right after adding a product
        does not race the still-settling page.
        """
        try:
            self.wait_for_row(self.sel("cart_rows"), product_name, present=True)
            return True
        except Exception:
            return False

    def assert_row_count(self, expected: int) -> None:
        """Wait until exactly `expected` product rows are shown."""
        self.wait_for_count(self.sel("cart_rows"), expected)

    def get_row_text(self, product_name: str) -> str:
        """Return the full text of the row containing `product_name`.

        This is the whole row (description, price, quantity, total), so assert
        containment against it rather than equality with a single field.
        """
        return self.row_containing(self.sel("cart_rows"), product_name).inner_text().strip()

    def is_empty(self) -> bool:
        """True once the 'Cart is empty!' message is shown. WAITS for it.

        This asserts the cart is empty ABSOLUTELY, so the calling scenario must
        own its starting state (fresh account or cleared cart).
        """
        return self.is_showing(self.sel("empty_cart_message"))
