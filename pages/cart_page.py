"""
CartPage — the /view_cart shopping cart screen.

Reads cart rows, quantities and prices; removes a product row by scoping to
the row that contains its name; reloads the cart; and detects the empty-cart
state. Selectors come from `pages.cart` in the app inventory — never a literal.

App: https://automationexercise.com
"""
from typing import List, Optional

from pages.base_page import BasePage


class CartPage(BasePage):
    """Shopping cart. Selectors: see `pages.cart` in the app inventory.

    The cart is server-owned state tied to the session/account, so an exact
    row count is safe to assert here (the cart belongs to this test's own
    session). To act on ONE product, scope to the row that contains its name
    rather than indexing a family selector, which would raise strict-mode.
    """

    INVENTORY_PAGE = "cart"

    # ── actions ──────────────────────────────────────────────
    def open_cart(self, base_url: str) -> None:
        """Navigate directly to the cart page."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.confirm_arrival()

    def reload_cart(self) -> None:
        """Full page refresh of the cart, then confirm we are still on it."""
        self.reload()
        self.confirm_arrival()

    def remove_product(self, product_name: str) -> None:
        """Remove the row whose description contains `product_name`.

        Scopes to the row containing the name and clicks the delete control
        inside it, so the family selector is never clicked as a whole.
        """
        self.click_in_row(
            self.sel("cart_rows"),
            product_name,
            self.sel("cart_delete_buttons"),
        )

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the cart table is on screen. WAITS for it.

        The cart table survives both the populated and post-add states, so it
        is a stable readiness signal. The empty-cart message is not — it is
        absent whenever the cart holds items.
        """
        return self.is_showing(self.sel("cart_table"), timeout_ms=timeout_ms)

    def confirm_arrival(self, **params: object) -> None:
        """Confirm the browser reached the cart page; recover if not."""
        super().confirm_arrival(**params)

    def get_product_names(self) -> List[str]:
        """Every product name currently in the cart, in row order."""
        return self.get_all_texts(self.sel("cart_product_names"))

    def has_product(self, product_name: str) -> bool:
        """True if a row containing `product_name` is present. WAITS for it."""
        return self.is_showing(self.sel("cart_table")) and any(
            product_name in name for name in self.get_product_names()
        )

    def assert_row_count(self, expected: int) -> None:
        """Wait until exactly `expected` product rows are present."""
        self.wait_for_count(self.sel("cart_rows"), expected)

    def get_row_text(self, product_name: str) -> str:
        """The full concatenated text of the row containing `product_name`.

        Returns the whole row (description, price, quantity, total), so assert
        containment against it, not equality with a single field value.
        """
        return self.row_containing(self.sel("cart_rows"), product_name).inner_text().strip()

    def is_empty(self) -> bool:
        """True once the 'Cart is empty!' message is shown. WAITS for it.

        Only true when the cart holds nothing — the mirror of the row family.
        Assert on it only when the scenario owns its starting state.
        """
        return self.is_showing(self.sel("empty_cart_message"))
