"""
CartPage — the shopping cart at /view_cart.

New page object for the cart-add-remove feature. Provides:

  - product-row PRESENCE, waiting so an assertion made right after an add or a
    removal does not race the page's own update (wait_for_row via BasePage)
  - per-row QUANTITY reads, scoped to the row that holds a named product
  - deleting a row by the product name it contains, scoping to that row rather
    than indexing a doubled family

The cart PERSISTS against a signed-in account and survives the run, so this
file never asserts an ABSOLUTE count or emptiness. Every reader here is
relative to a product this test named - "is this product present", "what is
its quantity" - which holds whatever the account started with. See the
cart page's persistent_state_note in the inventory.

App: https://automationexercise.com
"""
from typing import Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class CartPage(BasePage):
    """Shopping cart. Selectors: see `pages.cart` in the app inventory.

    The cart renders ONE of two mutually exclusive states: the row families
    when it holds items, or the empty-cart message when it does not. Readers
    here address a product by NAME, scoping the row-level families to the row
    that contains it rather than assuming a row index.
    """

    INVENTORY_PAGE = "cart"

    # ── actions ──────────────────────────────────────────────
    def open_cart(self, base_url: str) -> None:
        """Navigate directly to the cart page."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.confirm_arrival()

    def remove_product(self, product_name: str) -> None:
        """Delete the cart row that contains `product_name`.

        Scopes the delete control to the row holding the product name rather
        than indexing the delete family directly — the delete buttons are a
        multi-match family, so clicking the key as a whole raises a strict-mode
        violation. click_in_row() finds the right row and clicks the control
        inside it.
        """
        self.require_own_page()
        self.click_in_row(
            self.sel("cart_rows"),
            product_name,
            self.sel("cart_delete_buttons"),
        )
        # After deletion the row disappears; wait for that so a following
        # assertion reads the settled state rather than the stale row.
        self.wait_for_row(self.sel("cart_rows"), product_name, present=False)

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the cart table is on screen. WAITS for it.

        Probes the cart table, which is present whenever the cart page has
        rendered, independent of how many items it holds.
        """
        return self.is_showing(self.sel("cart_table"), timeout_ms=timeout_ms)

    def wait_until_contains(self, product_name: str) -> None:
        """Wait until a row for `product_name` is present. Raises on timeout.

        Call this where the product is EXPECTED to be in the cart — right after
        an add. It re-checks until the timeout, so it does not race the page's
        own update the way a one-shot name read would.
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=True)

    def wait_until_not_contains(self, product_name: str) -> None:
        """Wait until no row for `product_name` remains. Raises on timeout.

        The waiting form for ABSENCE: call it only where the product is
        expected to be gone — after a removal. It re-checks until the row has
        actually left the DOM.
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=False)

    def quantity_for(self, product_name: str) -> int:
        """Return the quantity shown in the row for `product_name`.

        WAITS for the row first so a read taken right after an add does not
        race the page. Scopes the quantity cell to the matching row via its
        index — the quantity selector is a per-row family and matches every
        row, so it must be addressed inside one row, not read as a whole.

        Returns an int so a step def can compare against the quantity its
        sentence names directly, without re-parsing a string.
        """
        self.require_own_page()
        self.wait_for_row(self.sel("cart_rows"), product_name, present=True)
        index = self.find_row_index_by_text(self.sel("cart_rows"), product_name)
        if index < 0:
            raise AssertionError(
                f"No cart row found for product {product_name!r}"
            )
        values = self.get_column_values(
            self.sel("cart_rows"), self.sel("cart_quantities"), 0
        )
        raw = values[index].strip()
        return int(raw)
