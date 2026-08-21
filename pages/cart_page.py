"""
CartPage — the shopping cart screen at /view_cart.

Selectors come from `pages.cart` in the app inventory. Never a literal here.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class CartPage(BasePage):
    """The cart. Selectors: see `pages.cart` in the app inventory.

    The cart PERSISTS against the signed-in account across logout and across
    runs, so an ABSOLUTE emptiness assertion is only safe when the scenario
    owns its starting state. Prefer relative assertions (the product this test
    added is present, or is gone) via wait_for_product_row().
    """

    INVENTORY_PAGE = "cart"

    # ── navigation ───────────────────────────────────────────
    def open_cart(self, base_url: str) -> None:
        """Navigate directly to the cart page."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    def confirm_arrival(self) -> None:
        """Confirm the browser reached the cart page; recover if it did not."""
        super().confirm_arrival()

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the cart table is on screen. WAITS for it."""
        return self.is_showing(self.sel("cart_table"), timeout_ms=timeout_ms)

    def product_names(self) -> list[str]:
        """Every product name currently in the cart, in DOM order."""
        return self.get_all_texts(self.sel("cart_product_names"))

    def wait_for_product_row(self, name: str, present: bool = True) -> None:
        """Wait until the row for `name` is present, or is gone.

        present=True after adding, present=False after removing. Waits rather
        than snapshotting, so it is reliable right after the action that
        changed the cart.
        """
        self.wait_for_row(self.sel("cart_rows"), name, present=present)

    def assert_row_count(self, expected: int) -> None:
        """Wait until exactly `expected` cart rows are present."""
        self.wait_for_count(self.sel("cart_rows"), expected)

    def is_empty(self) -> bool:
        """True once the 'Cart is empty!' message is shown. WAITS for it.

        Only meaningful when the scenario owns its starting state; the cart is
        persistent per account.
        """
        return self.is_showing(self.sel("empty_cart_message"))

    # ── actions ──────────────────────────────────────────────
    def remove_product(self, name: str) -> None:
        """Delete the cart row whose product name is `name`.

        Scopes to the row containing the name and clicks its delete control,
        so it never touches another row's X. No navigation follows.
        """
        self.click_in_row(
            self.sel("cart_rows"),
            name,
            self.sel("cart_delete_buttons"),
        )
