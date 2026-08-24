"""
ProductsPage — the /products listing and search screen.

Selectors come from the `products` page in the app inventory. This page
carries the full catalogue plus a search box; a search re-renders the same
page, swapping the "All Products" heading for "Searched Products".

App: https://automationexercise.com
"""
from typing import Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class ProductsPage(BasePage):
    """Product listing and search. Selectors: see `products` in the inventory.

    A search matching nothing renders NO result cards and NO empty-state
    message, so absence is asserted by counting cards, not by reading text.
    Several element families here are doubled per card (see the inventory
    notes) — never index across two families, always scope to the card that
    contains the product name.
    """

    INVENTORY_PAGE = "products"

    # ── actions ──────────────────────────────────────────────
    def open_listing(self, base_url: str) -> None:
        """Navigate directly to the products listing and confirm arrival."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.confirm_arrival()

    def search_for(self, term: str) -> None:
        """Type a search term and submit it. Confirms it is on this page first.

        Filling as the opening move without confirming the page would wait the
        full timeout and then blame the search field's selector.
        """
        self.require_own_page()
        self.fill(self.sel("search_input"), term)
        self.click(self.sel("search_button"))

    def open_product(self, product_name: str) -> None:
        """Open the detail page for the named product.

        The View Product links are a family (one per card) matched by href
        prefix, so scope to the card containing the product name rather than
        clicking the family. Arrival on the detail page is confirmed by the
        detail page's own page object, not here.
        """
        self.require_own_page()
        self.click_in_row(
            self.sel("product_cards"),
            product_name,
            self.sel("view_product_links"),
        )

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the products listing is on screen. WAITS for it.

        Probes the All Products heading, which is the listing's readiness
        signal in its unsearched state.
        """
        return self.is_showing(self.sel("all_products_heading"), timeout_ms=timeout_ms)

    def search_has_executed(self, timeout_ms: Optional[int] = None) -> bool:
        """True once a search has run. WAITS for the Searched Products heading.

        Call this only where a search IS expected to have executed. A result
        count alone cannot tell 'returned one product' from 'never ran'; the
        heading is the reliable signal that the search executed.
        """
        return self.is_showing(self.sel("searched_products_heading"), timeout_ms=timeout_ms)

    def get_result_names(self) -> list[str]:
        """Every visible product name in the current listing/results.

        The product-name family is doubled per card, so this may return each
        name twice — use it for containment checks, not for counting.
        """
        return self.get_all_texts(self.sel("product_names"))

    def get_result_card_count(self) -> int:
        """Number of product result cards currently rendered (snapshot).

        Uses the non-doubled product_cards family, so this is a true per-card
        count. A snapshot read, appropriate for branching or for asserting an
        empty result set once the search has been confirmed to have executed.
        """
        return self.get_count(self.sel("product_cards"))

    def has_result_for(self, product_name: str) -> bool:
        """True once a result card for the named product is present. WAITS.

        Call this only where the product IS expected among the results — it
        waits for at least one card, then checks the visible names. To assert a
        product is absent, use get_result_card_count() instead.
        """
        self.wait_for_any(self.sel("product_cards"))
        return any(product_name in name for name in self.get_result_names())
