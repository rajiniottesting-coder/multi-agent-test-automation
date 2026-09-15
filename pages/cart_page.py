"""
CartPage — the /view_cart shopping cart screen.

Selectors come from `pages.cart` in the app inventory. This page carries two
opposite states: while the cart holds items the row families render, and while
it is empty only the empty-cart message renders. Exactly one is present at a
time, so the row families are declared conditional in the inventory.

The cart PERSISTS against a registered account across logout and across runs,
so this page object offers RELATIVE row checks (a named row is present / is
gone) rather than absolute-count assertions. A scenario that has not cleared
or freshly created the account cannot honestly assert emptiness here.

App: https://automationexercise.com
"""
from typing import Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class CartPage(BasePage):
    """Shopping cart. Selectors: see `pages.cart` in the app inventory.

    Row-family keys (cart_rows, cart_product_names, cart_delete_buttons,
    cart_quantities) each match SEVERAL elements. Read them with the plural
    helpers; to act on ONE member, scope to the row containing the product
    name with click_in_row().
    """

    INVENTORY_PAGE = "cart"

    # ── actions ──────────────────────────────────────────────
    def open_cart(self, base_url: str) -> None:
        """Navigate directly to the cart page."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.confirm_arrival()

    def remove_product(self, product_name: str) -> None:
        """Delete the cart row for `product_name` via its 'x' control.

        Scopes to the row that contains the product name, then clicks the
        delete control inside that row — never the delete family as a whole,
        which would raise a strict-mode violation. Waits for the row to
        disappear so callers can assert absence immediately afterwards.
        """
        self.require_own_page()
        self.click_in_row(
            self.sel("cart_rows"),
            product_name,
            self.sel("cart_delete_buttons"),
        )
        self.wait_for_row(self.sel("cart_rows"), product_name, present=False)

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the cart table is on screen. WAITS for it.

        Call this only where the cart is expected to have loaded with content;
        on an empty cart the table is not rendered.
        """
        return self.is_showing(self.sel("cart_table"), timeout_ms=timeout_ms)

    def wait_for_product_row(self, product_name: str) -> None:
        """Wait until a cart row containing `product_name` is present.

        WAITS, and times out if the row never appears. Call this only where the
        product is expected in the cart — e.g. right after adding it.
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=True)

    def wait_for_product_row_absent(self, product_name: str) -> None:
        """Wait until no cart row contains `product_name`.

        WAITS for the row to be gone, then returns. The correct way to assert a
        removal: it re-checks until the timeout rather than reading a single
        stale snapshot right after the delete.
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=False)

    def get_product_names(self) -> list[str]:
        """Every product name currently in the cart, in order.

        cart_product_names is a column of single fields (one anchor per row),
        so reading its text yields the names rather than whole-row blobs.
        """
        return self.get_all_texts(self.sel("cart_product_names"))
