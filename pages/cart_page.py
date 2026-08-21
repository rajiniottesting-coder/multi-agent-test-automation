"""
CartPage — the /view_cart shopping cart screen.

Selectors come from `pages.cart` in the app inventory; this file never
contains a literal selector string. Methods are business verbs that read
the cart, remove a product row, and probe for the empty-cart state.

App: https://automationexercise.com
"""
from typing import List, Optional

from pages.base_page import BasePage


class CartPage(BasePage):
    """Shopping cart. Selectors: see `pages.cart` in the app inventory.

    The cart's row family (cart_rows), name family (cart_product_names) and
    delete-control family (cart_delete_buttons) each match SEVERAL elements,
    so they are never clicked or asserted on as a whole. To act on ONE
    product's row, scope to the row containing its name with click_in_row().
    """

    INVENTORY_PAGE = "cart"

    # ── navigation ───────────────────────────────────────────
    def open_cart(self, base_url: str) -> None:
        """Navigate directly to the /view_cart screen."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    def confirm_arrival(self, **params: object) -> None:
        """Confirm the browser reached the cart; recover the nav if not.

        Called by another page object's 'view cart' method after it clicks a
        link expected to land here, so an ad interstitial that swallowed the
        navigation is retried rather than silently timing out later.
        """
        super().confirm_arrival(**params)

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the cart table is on screen. WAITS for it.

        Probes the cart table, which is present whether the cart holds items
        or not, so it is a state-independent readiness signal.
        """
        return self.is_showing(self.sel("cart_table"), timeout_ms=timeout_ms)

    def get_product_names(self) -> List[str]:
        """Return every product name currently in the cart, in DOM order.

        Reads the cart_product_names family with the plural getter; safe on a
        multi-match key. Use containment checks against this list to assert a
        product IS present rather than indexing into it.
        """
        return self.get_all_texts(self.sel("cart_product_names"))

    def has_product(self, product_name: str) -> bool:
        """True if a cart row's name contains `product_name`."""
        return any(product_name in name for name in self.get_product_names())

    def get_row_count(self) -> int:
        """Number of product rows currently in the cart."""
        return self.get_count(self.sel("cart_rows"))

    def is_empty(self) -> bool:
        """True when the cart's own 'Cart is empty!' indicator is showing.

        Non-waiting probe on the empty-state element, which the app renders
        only when no products remain. Safe to call for asserting absence: it
        returns False instead of waiting when the message is not present.
        """
        return self.is_visible(self.sel("empty_cart_message"))

    # ── actions ──────────────────────────────────────────────
    def remove_product(self, product_name: str) -> None:
        """Delete the row whose product name contains `product_name`.

        Scopes to the row containing the name and clicks the delete control
        inside it, so the multi-match delete family is never clicked as a
        whole. Removal happens in place without a page navigation.
        """
        self.click_in_row(
            self.sel("cart_rows"),
            product_name,
            self.sel("cart_delete_buttons"),
        )
