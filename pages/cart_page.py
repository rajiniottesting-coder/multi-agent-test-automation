"""
CartPage — the shopping cart at /view_cart.

Selectors come from `pages.cart` in the app inventory; this file never contains
a literal selector string. Read each element via self.sel("<key>").

The cart PERSISTS against the signed-in account (see persistent_state_note in
the inventory), so this page object offers only RELATIVE readers — "is there a
row for this product?", "is that row gone?" — which are true whatever the
account started with. It deliberately does NOT offer an absolute
count/emptiness reader, because no scenario in this batch owns its starting
state.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class CartPage(BasePage):
    """The shopping cart. Selectors: see `pages.cart` in the app inventory.

    `cart_rows`, `cart_product_names` and `cart_delete_buttons` are all
    families (one member per cart row). Never click a family directly — scope
    to the row containing the product name with click_in_row(), and read
    presence/absence with wait_for_row().
    """

    INVENTORY_PAGE = "cart"

    # ── actions ──────────────────────────────────────────────
    def open_cart(self, base_url: str) -> None:
        """Navigate directly to the cart page and confirm arrival."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.confirm_arrival()

    def remove_product(self, product_name: str) -> None:
        """Delete the row for `product_name` from the cart.

        Scopes to the row that contains the product name and clicks the delete
        control inside it, so the correct row is removed regardless of its
        position or of any other rows the account already held.
        """
        self.click_in_row(
            self.sel("cart_rows"),
            product_name,
            self.sel("cart_delete_buttons"),
        )

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the cart table is on screen. WAITS for it.

        Probes the cart table container, which is present whether or not the
        cart holds items — the state-independent readiness signal for this
        page.
        """
        return self.is_showing(self.sel("cart_table"), timeout_ms=timeout_ms)

    def has_product_row(self, product_name: str) -> bool:
        """True once a cart row for `product_name` is present. WAITS for it.

        Call this only where the row is EXPECTED. It waits and times out if the
        row never appears, so it cannot be used to assert absence — use
        wait_until_product_removed() for that.
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=True)
        return True

    def wait_until_product_removed(self, product_name: str) -> bool:
        """True once no cart row for `product_name` remains. WAITS for the row
        to disappear.

        This is the waiting form for the ABSENCE case: after a removal the
        table is still settling, so a one-shot read races the update. It
        re-checks until the row is gone.
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=False)
        return True

    def get_product_names(self) -> list[str]:
        """Visible product names currently in the cart, in DOM order.

        Reads the product-name column (a single field per row), which is a
        correct use of get_all_texts on a column family.
        """
        return self.get_all_texts(self.sel("cart_product_names"))
