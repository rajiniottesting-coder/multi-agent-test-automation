"""
CartPage — the shopping cart at /view_cart.

Selectors: see `pages.cart` in the app inventory. This page holds state that
PERSISTS against the signed-in account across logout and across runs, so
absolute assertions ('cart is empty', 'exactly N rows') are only safe when the
scenario owns its starting state. The shopping-session scenario does NOT own
its starting state, so this page object offers RELATIVE membership checks:
the product this test added is present, or is gone. Those hold whatever the
account's cart started with.

App: https://automationexercise.com
"""
from typing import Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class CartPage(BasePage):
    """Shopping cart. Selectors: see `pages.cart` in the app inventory."""

    INVENTORY_PAGE = "cart"

    # ── actions ──────────────────────────────────────────────
    def open_cart(self, base_url: str) -> None:
        """Navigate directly to the cart page.

        Ends by confirming arrival, so an ad interstitial that swallowed the
        navigation is recovered rather than blamed on the next step's selector.
        """
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.confirm_arrival()

    def remove_product(self, product_name: str) -> None:
        """Delete the cart row whose description contains `product_name`.

        Scopes to the row containing the product name and clicks the delete
        control inside it, rather than indexing the delete-button family — the
        two families are not guaranteed to run in lockstep, so scoping by text
        is the safe way to act on one member.
        """
        self.click_in_row(
            self.sel("cart_rows"),
            product_name,
            self.sel("cart_delete_buttons"),
        )

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the cart table is on screen. WAITS for it.

        The cart table is present whether the cart has items or not, so it is a
        state-independent readiness signal — unlike the empty-cart message or
        the row family, each of which is true in only one of the two states.
        """
        return self.is_showing(self.sel("cart_table"), timeout_ms=timeout_ms)

    def wait_for_product_present(
        self, product_name: str, timeout_ms: Optional[int] = None
    ) -> None:
        """Wait until a cart row containing `product_name` is present.

        WAITS. Call this straight after adding the product — the row family is
        still settling at that moment, so a snapshot read would race it. A
        relative check: it does not care what else is in the cart.
        """
        self.wait_for_row(
            self.sel("cart_rows"), product_name, present=True, timeout_ms=timeout_ms
        )

    def wait_for_product_absent(
        self, product_name: str, timeout_ms: Optional[int] = None
    ) -> None:
        """Wait until no cart row containing `product_name` remains.

        WAITS for the removal to take effect (present=False). Call this after
        deleting the product; a snapshot read immediately after the click can
        still see the row mid-removal. A relative check: other rows from the
        account's history may legitimately remain.
        """
        self.wait_for_row(
            self.sel("cart_rows"), product_name, present=False, timeout_ms=timeout_ms
        )

    def get_cart_product_names(self) -> list[str]:
        """Every product name currently listed in the cart, in DOM order."""
        return self.get_all_texts(self.sel("cart_product_names"))
