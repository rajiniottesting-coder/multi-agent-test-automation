"""
CartPage — the shopping cart at /view_cart.

Selectors come from `pages.cart` in the app inventory; this file never writes a
literal selector. Business verbs only, every one built on a BasePage helper.

The cart is a FAMILY of rows (cart_rows, cart_product_names, cart_delete_buttons
all match several elements), so a scenario that acts on one product scopes to
the row containing its name via BasePage helpers rather than indexing blindly.

App: https://automationexercise.com
"""
from typing import List, Optional

from pages.base_page import BasePage


class CartPage(BasePage):
    """Shopping cart. Selectors: see `pages.cart` in the app inventory."""

    INVENTORY_PAGE = "cart"

    # ── navigation / readiness ───────────────────────────────
    def open_cart(self, base_url: str) -> None:
        """Navigate directly to the cart page."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    def confirm_arrival(self, **params: object) -> None:
        """Confirm the browser reached the cart, recovering from an ad if not.

        Overrides BasePage to read THIS page's declared URL; a method on another
        page object that clicks through to the cart ends by calling this.
        """
        super().confirm_arrival(**params)

    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the cart table is on screen. WAITS for it.

        The cart_table id is the most state-independent element on the page: it
        is present whether the cart holds rows or shows the empty message.
        """
        return self.is_showing(self.sel("cart_table"), timeout_ms=timeout_ms)

    def reload_cart(self) -> None:
        """Full page refresh of the cart, for persistence scenarios."""
        self.reload()

    # ── row queries ──────────────────────────────────────────
    def product_names(self) -> List[str]:
        """Every product name currently in the cart, in DOM order."""
        return self.get_all_texts(self.sel("cart_product_names"))

    def assert_row_count(self, expected: int) -> None:
        """Wait until the cart holds exactly `expected` rows.

        Uses wait_for_count, not a snapshot: this is called right after an add
        or a delete, when the page is still settling.
        """
        self.wait_for_count(self.sel("cart_rows"), expected)

    def wait_for_product(self, product_name: str, present: bool = True) -> None:
        """Wait until a row for `product_name` is there, or is gone.

        `present=True` after adding, `present=False` after removing. Re-checks
        until the timeout rather than reading the list once.
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=present)

    def get_product_row_text(self, product_name: str) -> str:
        """Concatenated text of the row containing `product_name`.

        The whole row: description, price, quantity and total. Assert with
        containment (`Rs. 500` in it), never equality against one field.
        """
        return self.row_containing(self.sel("cart_rows"), product_name).inner_text().strip()

    # ── actions ──────────────────────────────────────────────
    def remove_product(self, product_name: str) -> None:
        """Click the delete control on the row that contains `product_name`."""
        self.click_in_row(
            self.sel("cart_rows"),
            product_name,
            self.sel("cart_delete_buttons"),
        )

    # ── empty-state ──────────────────────────────────────────
    def is_empty(self) -> bool:
        """True once the 'Cart is empty!' message is shown. WAITS for it.

        Assert emptiness with this, not by counting rows: the message is the
        application's own empty-state indicator. Only meaningful when the
        scenario owns its starting cart state.
        """
        return self.is_showing(self.sel("empty_cart_message"))
