"""
CartPage — the shopping cart at /view_cart.

Selectors live in the app inventory under `pages.cart`; this file never
holds a literal selector. Set INVENTORY_PAGE and resolve every element via
self.sel("<key>").

The cart belongs to the current session/account, so an EXACT row count is
safe to assert here (see the inventory's _test_owned note). The empty-cart
message and the row family are mirror states — exactly one is present at any
moment — so absence of the product is asserted via the empty-cart message
or the non-waiting row probe, never by waiting for a row that will never come.

App: https://automationexercise.com
"""
from typing import List

from pages.base_page import BasePage


class CartPage(BasePage):
    """Cart page. Selectors: see `pages.cart` in the app inventory.

    cart_rows, cart_product_names and cart_delete_buttons are MULTI-MATCH
    families — read them with the plural helpers, and act on ONE member by
    scoping to the row that contains the product name via click_in_row().
    """

    INVENTORY_PAGE = "cart"

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self) -> bool:
        """True once the cart table is on screen. WAITS for it.

        The cart table is present whether the cart holds items or is empty,
        so it is the state-independent readiness signal for this page.
        """
        return self.is_showing(self.sel("cart_table"))

    def get_product_names(self) -> List[str]:
        """Visible product names for every row in the cart, in DOM order."""
        return self.get_all_texts(self.sel("cart_product_names"))

    def get_row_count(self) -> int:
        """Number of product rows currently in the cart."""
        return self.get_count(self.sel("cart_rows"))

    def has_product(self, product_name: str) -> bool:
        """True if a row for the given product is present. Never waits."""
        return any(product_name in name for name in self.get_product_names())

    def get_row_text(self, product_name: str) -> str:
        """Full text of the row containing `product_name`.

        The whole row concatenates description, price, quantity and total, so
        callers assert containment (price/quantity in the returned blob), not
        equality against a single field.
        """
        row = self.row_containing(self.sel("cart_rows"), product_name)
        return row.inner_text().strip()

    def is_empty(self) -> bool:
        """True if the cart shows its empty-state message. Never waits.

        The empty-cart message and the row family are mutually exclusive, so
        this is the correct absolute empty-state assertion — it does not wait
        for rows that will never appear.
        """
        return self.is_visible(self.sel("empty_cart_message"))

    # ── actions ──────────────────────────────────────────────
    def remove_product(self, product_name: str) -> None:
        """Delete the row for `product_name` via its X control.

        Scopes the click to the row containing the product name rather than
        indexing into the delete-button family, so it stays correct however
        the rows are ordered.
        """
        self.click_in_row(
            self.sel("cart_rows"),
            product_name,
            self.sel("cart_delete_buttons"),
        )
