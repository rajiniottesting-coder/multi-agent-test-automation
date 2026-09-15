"""
ProductsPage — the All Products / search listing screen.

Selectors come from the `products` page in the app inventory. This page
carries several FAMILY selectors (product cards, names, view-product links,
add-to-cart buttons); read them with the plural helpers and act on ONE member
by scoping to the row/card that contains the product name.

App: https://automationexercise.com
"""
from typing import Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class ProductsPage(BasePage):
    """All Products listing and search. Selectors: `products` in the inventory.

    Two readiness signals matter and mean different things:
      - all_products_heading is present on the unsearched listing AND after an
        EMPTY search (which does not actually run a search).
      - searched_products_heading appears only after a real search has run.
    Choose the one that matches the state you are asserting.
    """

    INVENTORY_PAGE = "products"

    # ── navigation ───────────────────────────────────────────
    def open_products(self, base_url: str) -> None:
        """Navigate directly to the products listing."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.confirm_arrival()

    # ── actions ──────────────────────────────────────────────
    def search_for(self, term: str) -> None:
        """Type a search term and submit it.

        This is the first action of the method, so it confirms it is on this
        page before touching the field: filling a field that is not on screen
        would waste the full Playwright timeout and then blame the field.
        """
        self.require_own_page()
        self.fill(self.sel("search_input"), term)
        self.click(self.sel("search_button"))

    def submit_empty_search(self) -> None:
        """Clear the search box and submit with no term.

        Per the inventory, this does NOT run a search — the full catalogue
        stays shown and all_products_heading remains in place.
        """
        self.require_own_page()
        self.clear(self.sel("search_input"))
        self.click(self.sel("search_button"))

    def open_product(self, product_name: str) -> None:
        """Open a product's detail page via its View Product link.

        view_product_links is a family (one per card), so this scopes to the
        card containing the product name rather than clicking the family.
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

        Uses all_products_heading, which is present on the freshly loaded
        listing — the most state-independent readiness signal for arrival on
        this page before any search has run.
        """
        return self.is_showing(self.sel("all_products_heading"), timeout_ms=timeout_ms)

    def has_product(self, product_name: str) -> bool:
        """True once a card for `product_name` is present. WAITS for it.

        Call this only where the product IS expected. To assert a product is
        absent, use has_no_product_cards() (empty search returns no cards).
        """
        self.wait_for_row(self.sel("product_cards"), product_name, present=True)
        return True

    def has_full_catalogue(self) -> bool:
        """True once the unsearched catalogue is shown. WAITS for it.

        An empty search leaves all_products_heading in place, so its presence
        is the signal that the full catalogue is still being displayed rather
        than a filtered result set. Call this only where the full catalogue is
        the expected state.
        """
        return self.is_showing(self.sel("all_products_heading"))

    def has_no_product_cards(self) -> bool:
        """True once NO product cards are rendered. WAITS for the count to
        settle at zero, then returns.

        Call this only where zero cards is the EXPECTED state — a search term
        matching no product renders no cards (this site has no explicit
        'no results' message). wait_for_count retries until the count is
        exactly zero and logs the reason if it never settles, so a step
        asserting on this cannot race the search request finishing.
        """
        self.wait_for_count(self.sel("product_cards"), 0)
        return True
