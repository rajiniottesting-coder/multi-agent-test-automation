"""
CartPage — the shopping cart at /view_cart.

Page object for the cart. Exposes product-presence checks, per-row removal and
an empty-cart assertion helper.

Conventions (see pages/login_page.py for the worked reference):
  - Selectors come from the app inventory via self.sel("<key>"), never literals.
  - Methods are business verbs describing intent, not UI mechanics.
  - No assertions here — those belong in the step definitions.
  - Family selectors (cart_rows, cart_product_names, cart_delete_buttons) are
    read with the plural helpers or scoped to one row with click_in_row();
    they are never clicked or asserted on as a whole.

App: https://automationexercise.com
"""
from typing import List, Optional

from pages.base_page import BasePage


class CartPage(BasePage):
    """The cart. Selectors: see `pages.cart` in the app inventory."""

    INVENTORY_PAGE = "cart"

    # ── navigation ───────────────────────────────────────────
    def open_cart(self, base_url: str) -> None:
        """Navigate directly to the cart page."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.confirm_arrival()

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the cart table is on screen. WAITS for it."""
        return self.is_showing(self.sel("cart_table"), timeout_ms=timeout_ms)

    def get_product_names(self) -> List[str]:
        """Return the names of every product currently in the cart."""
        return self.get_all_texts(self.sel("cart_product_names"))

    def has_product(self, product_name: str) -> bool:
        """True if a row for the given product is present in the cart."""
        return any(product_name in name for name in self.get_product_names())

    def get_row_count(self) -> int:
        """Number of product rows currently in the cart."""
        return self.get_count(self.sel("cart_rows"))

    def is_empty(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the 'Cart is empty!' message is shown. WAITS for it.

        Rendered only when the cart holds nothing — the mirror of cart_rows,
        and exactly one of the two is present at any moment.
        """
        return self.is_showing(self.sel("empty_cart_message"), timeout_ms=timeout_ms)

    # ── actions ──────────────────────────────────────────────
    def remove_product(self, product_name: str) -> None:
        """Click the delete control on the row containing the given product.

        Scopes to the row by product name rather than assuming an index — the
        delete control is a per-row family and must not be clicked as a whole.
        """
        self.click_in_row(
            self.sel("cart_rows"),
            product_name,
            self.sel("cart_delete_buttons"),
        )
