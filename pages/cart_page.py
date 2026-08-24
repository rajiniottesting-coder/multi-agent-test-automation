"""
CartPage — the /view_cart shopping cart screen.

Selectors come from `pages.cart` in the app inventory; this file never
contains a literal selector string. Set INVENTORY_PAGE, then look each
element up by its inventory KEY with self.sel("<key>").

The cart PERSISTS for a registered account across logout and across runs,
so a scenario reusing a shared account cannot assert the cart is empty
absolutely — it must assert RELATIVELY: that the product this test added
is present, or that the product this test removed is gone. This page object
therefore exposes waiting presence/absence helpers scoped to a named
product, plus quantity and price readers for a single row.

App: https://automationexercise.com
"""
from typing import Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class CartPage(BasePage):
    """Shopping cart. Selectors: see `pages.cart` in the app inventory.

    Row family is `cart_rows`; per-row cells (`cart_product_names`,
    `cart_quantities`) are read RELATIVE to a row, never with an absolute
    single-cell selector. To act on one product's row (e.g. delete it),
    scope to the row containing that product's name.
    """

    INVENTORY_PAGE = "cart"

    # ── actions ──────────────────────────────────────────────
    def open_cart(self, base_url: str) -> None:
        """Navigate directly to the /view_cart page."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.confirm_arrival()

    def remove_product(self, product_name: str) -> None:
        """Click the delete control on the row for `product_name`.

        Scopes to the row containing the product name rather than indexing a
        delete-button family, so the correct row is removed even when the
        cart holds other products.
        """
        self.require_own_page()
        self.click_in_row(
            self.sel("cart_rows"),
            product_name,
            self.sel("cart_delete_buttons"),
        )

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the cart table is on screen. WAITS for it.

        Probes the cart table container, which is present whether or not the
        cart has rows, so it is a state-independent readiness signal.
        """
        return self.is_showing(self.sel("cart_table"), timeout_ms=timeout_ms)

    def has_product(self, product_name: str, timeout_ms: Optional[int] = None) -> bool:
        """True once a row for `product_name` is present. WAITS for it.

        Call this only where the product is EXPECTED to be present — it waits
        up to the timeout for the row to appear. To assert a product is
        absent, use wait_until_product_absent() instead, which waits for the
        row to be gone rather than for it to appear.
        """
        self.wait_for_row(
            self.sel("cart_rows"),
            product_name,
            present=True,
            timeout_ms=timeout_ms,
        )
        return True

    def wait_until_product_absent(
        self, product_name: str, timeout_ms: Optional[int] = None
    ) -> bool:
        """True once no row for `product_name` remains. WAITS for removal.

        Use this after removing a product: it re-checks until the row is gone,
        so it reports the settled state rather than a snapshot taken while the
        cart is still updating.
        """
        self.wait_for_row(
            self.sel("cart_rows"),
            product_name,
            present=False,
            timeout_ms=timeout_ms,
        )
        return True

    def get_quantity_for(self, product_name: str) -> str:
        """Return the quantity cell text for `product_name`'s row.

        The quantity selector is scoped INSIDE the row (per the inventory
        note), so it is read via the row index rather than an absolute
        single-cell selector.
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=True)
        index = self.find_row_index_by_text(self.sel("cart_rows"), product_name)
        return self.get_cell_text(
            self.sel("cart_rows"), index, self.sel("cart_quantities"), 0
        )

    def get_price_for(self, product_name: str) -> str:
        """Return the description-cell text for `product_name`'s row.

        The cart has no isolated per-row PRICE cell key in the inventory —
        only `cart_product_names` (the description link) and `cart_quantities`
        are cell-scoped. This returns the description cell, which carries the
        product name/link text; it is NOT a clean price value. Callers should
        assert price on the product detail page, which exposes a price
        reader, rather than on this cell.
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=True)
        index = self.find_row_index_by_text(self.sel("cart_rows"), product_name)
        return self.get_cell_text(
            self.sel("cart_rows"), index, self.sel("cart_product_names"), 0
        )

    def get_product_names(self) -> list[str]:
        """Return every product name currently in the cart, in row order."""
        return self.get_all_texts(self.sel("cart_product_names"))
