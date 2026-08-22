"""
CartPage — the shopping cart at /view_cart.

Selectors: see `pages.cart` in the app inventory. No literal selectors here —
every element is looked up by its inventory key with self.sel("<key>").

The cart PERSISTS against a signed-in account, so absolute assertions (exact
row count, cart-is-empty) are only honest when the scenario owns its starting
state. empty_the_cart() is provided for that purpose.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class CartPage(BasePage):
    """Shopping cart. Selectors: see `pages.cart` in the app inventory.

    cart_rows / cart_product_names / cart_delete_buttons are MULTI-MATCH
    families (one per product). Never click, fill or assert on them as a whole:
    scope to the row containing the product name with click_in_row(), or read
    them with the plural helpers.
    """

    INVENTORY_PAGE = "cart"

    # ── actions ──────────────────────────────────────────────
    def open_cart(self, base_url: str) -> None:
        """Navigate directly to the cart page."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.confirm_arrival()

    def remove_product(self, product_name: str) -> None:
        """Delete the row for `product_name` by scoping to that row's X control.

        Removal re-renders the cart in place, no navigation. Assert the row is
        gone afterwards with is_product_in_cart(present=False) / a waiting probe.
        """
        self.click_in_row(
            self.sel("cart_rows"),
            product_name,
            self.sel("cart_delete_buttons"),
        )
        self.wait_for_row(self.sel("cart_rows"), product_name, present=False)

    def empty_the_cart(self) -> None:
        """Remove every entry, leaving the cart genuinely empty.

        Bind this to a Given so a scenario can OWN its starting state; after it
        an absolute 'cart is empty' assertion is honest. Re-reads the list after
        each removal, since the cart re-renders in place.
        """
        while self.get_count(self.sel("cart_delete_buttons")) > 0:
            self.click_nth(self.sel("cart_delete_buttons"), 0)
            # Wait for the count to drop before the next iteration reads it.
            self.wait_for_count(
                self.sel("cart_delete_buttons"),
                self.get_count(self.sel("cart_delete_buttons")) - 1,
            )

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the cart table is on screen. WAITS for it.

        Call where the cart page is expected. The cart table is present whether
        the cart holds items or is empty, so it is a state-independent readiness
        signal.
        """
        return self.is_showing(self.sel("cart_table"), timeout_ms=timeout_ms)

    def get_product_names(self) -> list[str]:
        """Every product name currently in the cart, in order."""
        return self.get_all_texts(self.sel("cart_product_names"))

    def wait_for_product(self, product_name: str, present: bool = True) -> None:
        """Wait until the row for `product_name` is present, or is gone.

        present=True after adding, present=False after removing. Re-checks until
        the timeout — reading a snapshot right after the action that changed the
        cart races the re-render.
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=present)

    def get_row_text_for(self, product_name: str) -> str:
        """The whole cart ROW containing `product_name`, cells concatenated.

        Returns the entire row's text (description, price, quantity, total run
        together), NOT a single field. Assert containment against it — e.g.
        that the price 'Rs. 500' and quantity '1' both appear — never equality.
        """
        return self.row_containing(self.sel("cart_rows"), product_name).inner_text()

    def assert_row_count(self, expected: int) -> None:
        """Wait until exactly `expected` product rows are shown.

        Safe to assert absolutely: the cart is private to this test's session.
        Uses wait_for_count so it survives the cart re-render after an add or
        removal.
        """
        self.wait_for_count(self.sel("cart_rows"), expected)

    def is_empty(self) -> bool:
        """True once the cart shows its empty-state message. WAITS, and times
        out if it is not empty.

        Call this only where emptiness is the EXPECTED answer — a scenario that
        owns its starting state (registered fresh, or emptied the cart first). A
        step asking 'is it empty?' to branch on the reply would pay the full
        timeout every time the cart still has items.
        """
        return self.is_showing(self.sel("empty_cart_message"))
