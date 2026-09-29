"""
ProductsPage — the All Products / search listing screen.

Selectors come from `pages.products` in the app inventory; this file never
holds a literal selector string. Methods are business verbs that name what
they act on.

App: https://automationexercise.com
"""
from typing import Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class ProductsPage(BasePage):
    """All Products listing and product search.

    Readiness is a state-independent element. The listing swaps its heading
    between 'All Products' (unsearched) and 'Searched Products' (after a
    search), and an empty search renders no cards at all — so the search box
    is the one control present in every state and is used for is_loaded().
    """

    INVENTORY_PAGE = "products"

    # ── actions ──────────────────────────────────────────────
    def open_listing(self, base_url: str) -> None:
        """Navigate to the All Products listing."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.confirm_arrival()

    def search_for(self, term: str) -> None:
        """Enter a search term and submit it.

        Filling is the first action, so make sure the browser is on this page
        first — filling a field that is not on screen would wait the full
        timeout and then blame the locator rather than the wrong page.
        """
        self.require_own_page()
        self.fill(self.sel("search_input"), term)
        self.click(self.sel("search_button"))

    def open_product(self, name: str) -> None:
        """Open the detail page for the search result whose card contains
        `name`, via that card's View Product link.

        Scopes to the card containing the product name rather than indexing
        into the View Product family — the product cards family is NOT doubled
        while the add-to-cart and name families are, so an index taken from a
        doubled family would address the wrong link.
        """
        self.require_own_page()
        self.click_in_row(
            self.sel("product_cards"),
            name,
            self.sel("view_product_links"),
        )

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the products listing is on screen. WAITS for it.

        Probes the search box, the one control present in every listing state
        (unsearched, searched-with-results, searched-empty).
        """
        return self.is_showing(self.sel("search_input"), timeout_ms=timeout_ms)

    def has_search_result_for(self, name: str) -> bool:
        """True once a result card containing `name` is shown. WAITS.

        Call this only where the product IS expected to be found; the wait
        will time out if it never appears. For asserting NO results, use
        get_result_count() instead.
        """
        self.wait_for_row(self.sel("product_cards"), name, present=True)
        return True

    def get_result_count(self) -> int:
        """Number of product cards currently shown.

        For asserting an EMPTY result: the app renders no cards for a
        no-match search (there is no empty-state message), so a card count of
        zero is the correct signal. Wait for the search to have actually run
        (the 'Searched Products' heading) before counting, so an early read
        does not count the full catalogue from before the search executed.
        """
        self.wait_visible(self.sel("searched_products_heading"))
        return self.get_count(self.sel("product_cards"))
