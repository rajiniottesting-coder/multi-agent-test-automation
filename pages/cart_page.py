"""
CartPage — the shopping cart screen at /view_cart.

Verifies which products a session has in its cart, removes a product by name,
and confirms the cart is empty. Selectors: see `pages.cart` in the app
inventory. No literal selectors live here — every one is resolved through
self.sel("<key>").

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class CartPage(BasePage):
    """The shopping cart. Selectors: see `pages.cart` in the app inventory.

    The cart family selectors (rows, product names, delete buttons) each match
    SEVERAL elements. Read the family with get_all_texts / get_count; act on a
    single member by scoping to the row containing the product name with
    click_in_row(). Never click, fill or assert on a family as a whole.
    """

    INVENTORY_PAGE = "cart"

    # ── readiness ────────────────────────────────────────────
    def confirm_arrival(self, **params: object) -> None:
        """Confirm the browser reached the cart, recovering if an ad ate the
        navigation. Called by methods on OTHER pages that click through to
        this one."""
        super().confirm_arrival(**params)

    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the cart table is on screen. WAITS for it.

        Probes the cart table, which is present whether the cart holds items
        or is empty — a state-independent readiness signal."""
        return self.is_showing(self.sel("cart_table"), timeout_ms=timeout_ms)

    # ── queries ──────────────────────────────────────────────
    def has_product(self, product_name: str) -> bool:
        """True if a cart row for the named product is present. WAITS for it.

        Uses the row family (multi-match) and checks containment against every
        row's text, so a partial match on the product name is sufficient."""
        self.wait_visible(self.sel("cart_table"))
        return any(
            product_name in text
            for text in self.get_all_texts(self.sel("cart_rows"))
        )

    def get_product_names(self) -> list[str]:
        """Return the product names of every row currently in the cart."""
        return self.get_all_texts(self.sel("cart_product_names"))

    def get_row_containing_text(self, product_name: str) -> str:
        """Return the full text of the first cart row containing the name.

        A row selector matches the WHOLE row — id, description, price,
        quantity and total concatenated — so callers assert containment on
        this blob, never equality against a single field."""
        return self.row_containing(self.sel("cart_rows"), product_name).inner_text().strip()

    def is_empty(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the 'Cart is empty!' message is shown. WAITS for it.

        The empty-state message and the cart rows are mutually exclusive — the
        app renders exactly one of the two — so this is the reliable assertion
        for an emptied cart, not a row count of zero."""
        return self.is_showing(self.sel("empty_cart_message"), timeout_ms=timeout_ms)

    # ── actions ──────────────────────────────────────────────
    def remove_product(self, product_name: str) -> None:
        """Remove the named product by clicking the delete control in its row.

        Scopes to the row containing the product name and clicks its own
        delete control, rather than indexing into the delete-button family —
        which guarantees the correct product is removed even if row order
        differs."""
        self.click_in_row(
            self.sel("cart_rows"),
            product_name,
            self.sel("cart_delete_buttons"),
        )
