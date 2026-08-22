"""
CartPage — the shopping cart at /view_cart.

Inspects the cart's rows, reads product name and price for a given product,
removes a product row and reports whether the cart is empty.

Selectors come from `pages.cart` in the app inventory; this file never holds a
literal selector string. Every method uses a BasePage helper.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class CartPage(BasePage):
    """The shopping cart. Selectors: see `pages.cart` in the app inventory.

    The cart persists against a registered account across logout and across
    runs, so an ABSOLUTE emptiness assertion is only valid when the scenario
    owns its starting state. Prefer the relative row-presence helpers when it
    does not.
    """

    INVENTORY_PAGE = "cart"

    # ── actions ──────────────────────────────────────────────
    def open_cart(self, base_url: str) -> None:
        """Navigate directly to the cart page."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.confirm_arrival()

    def remove_product(self, product_name: str) -> None:
        """Delete the cart row for `product_name` by clicking its X control.

        Scopes to the row containing the product name rather than indexing into
        the delete-button family, which is a multi-match selector.
        """
        self.click_in_row(
            self.sel("cart_rows"),
            product_name,
            self.sel("cart_delete_buttons"),
        )

    # ── waits ────────────────────────────────────────────────
    def wait_for_product_row(self, product_name: str, present: bool = True) -> None:
        """Wait until a cart row for `product_name` is there, or is gone.

        Pass present=False after a removal — it waits for the row to disappear
        and returns the moment it does, instead of snapshotting a list that may
        still be settling.
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=present)

    def assert_row_count(self, expected: int) -> None:
        """Wait until exactly `expected` product rows are present.

        Uses wait_for_count so the assertion survives the page still updating
        immediately after an add or remove.
        """
        self.wait_for_count(self.sel("cart_rows"), expected)

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the cart table is on screen. WAITS for it.

        Delegates to is_showing so a failed readiness check logs the selector,
        the wait it used and the current URL.
        """
        return self.is_showing(self.sel("cart_table"), timeout_ms=timeout_ms)

    def has_product(self, product_name: str) -> bool:
        """True once a cart row for `product_name` is present. WAITS for it.

        Call this only where the product is expected to BE in the cart; it can
        only answer 'no' by timing out. To assert a product is gone, use
        wait_for_product_row(product_name, present=False).
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=True)
        return True

    def product_names(self) -> list[str]:
        """Every product name currently in the cart, in DOM order."""
        return self.get_all_texts(self.sel("cart_product_names"))

    def row_text(self, product_name: str) -> str:
        """The full text of the cart row containing `product_name`.

        Returns the concatenated text of the whole row — name, price, quantity
        and the rest — so assert containment against it, not equality with a
        single field.
        """
        return self.row_containing(self.sel("cart_rows"), product_name).inner_text().strip()

    def is_empty(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the 'Cart is empty!' message is on screen. WAITS for it.

        Call this only where emptiness is the expected answer — it can only
        report 'no' by exhausting its timeout. Emptiness is ABSOLUTE state, so
        the scenario must own its starting cart (a fresh account or an
        explicitly cleared cart) for this to be meaningful.
        """
        return self.is_showing(self.sel("empty_cart_message"), timeout_ms=timeout_ms)
