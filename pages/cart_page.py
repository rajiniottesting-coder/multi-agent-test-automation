"""
CartPage — the shopping cart at /view_cart.

Reads cart rows, removes a product row by name, reloads the page, and detects
the empty-cart message. Selectors come from the `cart` page in the app
inventory; this file never contains a literal selector.

App: https://automationexercise.com
"""
from typing import List, Optional

from pages.base_page import BasePage


class CartPage(BasePage):
    """View Cart. Selectors: see `pages.cart` in the app inventory.

    The cart is session/account-owned server state, so an exact row count is
    safe ONLY when the scenario owns its starting state (fresh session). The
    cart-management scenarios begin from a fresh browser session, so the
    absolute-count and empty-cart assertions here are valid.
    """

    INVENTORY_PAGE = "cart"

    # ── navigation ───────────────────────────────────────────
    def open_cart(self, base_url: str) -> None:
        """Navigate directly to the cart page."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    def confirm_arrival(self, **params: object) -> None:
        """Confirm the browser reached the cart page; recover if not."""
        super().confirm_arrival(**params)

    def refresh(self) -> None:
        """Reload the cart page (full page refresh)."""
        self.reload()

    # ── actions ──────────────────────────────────────────────
    def remove_product(self, product_name: str) -> None:
        """Remove the cart row for the named product via its delete control.

        Scopes to the row containing the product name so exactly one delete
        control is clicked, never the whole family.
        """
        self.click_in_row(
            self.sel("cart_rows"),
            product_name,
            self.sel("cart_delete_buttons"),
        )
        self.wait_for_row(self.sel("cart_rows"), product_name, present=False)

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the cart table is on screen. WAITS for it.

        The cart table is present whether the cart has items or is empty-bound,
        so it is a state-independent readiness signal for this page.
        """
        return self.is_showing(self.sel("cart_table"), timeout_ms=timeout_ms)

    def get_product_names(self) -> List[str]:
        """Every product name currently in the cart, in row order."""
        return self.get_all_texts(self.sel("cart_product_names"))

    def has_product(self, product_name: str) -> bool:
        """True once a row containing the product name is present. WAITS.

        Suitable for asserting a product IS in the cart, including after a
        reload or navigating away and back.
        """
        try:
            self.wait_for_row(self.sel("cart_rows"), product_name, present=True)
            return True
        except Exception:
            return False

    def assert_row_count(self, expected: int) -> None:
        """Wait until exactly `expected` product rows are present."""
        self.wait_for_count(self.sel("cart_rows"), expected)

    def get_row_text(self, product_name: str) -> str:
        """The full text of the row containing the product name.

        Returns the concatenated text of every cell in that row (name, price,
        quantity, total). Assert containment against it, not equality.
        """
        row = self.row_containing(self.sel("cart_rows"), product_name)
        return (row.inner_text() or "").strip()

    def is_empty(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the 'Cart is empty!' message is shown. WAITS.

        The empty-cart message renders only when the cart holds nothing, so
        this is an absolute assertion — valid here because the cart-management
        scenarios own their starting state (fresh session).
        """
        return self.is_showing(self.sel("empty_cart_message"), timeout_ms=timeout_ms)
