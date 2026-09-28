"""
ProductsPage — the All Products listing and search-results screen.

Selectors come from the app inventory (`pages.products`); this file never
carries a literal selector. See pages/login_page.py for the conventions this
follows.

App: https://automationexercise.com
"""
from typing import Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class ProductsPage(BasePage):
    """All Products listing and search results.

    Selectors: see `pages.products` in the app inventory.

    Two headings signal state. `all_products_heading` is on the unsearched
    catalogue and stays put when an EMPTY query is submitted (an empty query
    does not run a search). `searched_products_heading` replaces it only once a
    real term has been entered and submitted — that is the reliable "the search
    executed" signal, because a card count alone cannot tell a one-result
    search from a search that never ran.
    """

    INVENTORY_PAGE = "products"

    # ── actions ──────────────────────────────────────────────
    def open_listing(self, base_url: str) -> None:
        """Navigate directly to the Products listing."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.confirm_arrival()

    def search_for(self, term: str) -> None:
        """Enter a search term and submit it.

        Filling is the first action here, so confirm the browser is on this
        page first — filling a field that is not on screen waits the full
        timeout and then blames the field rather than the page.
        """
        self.require_own_page()
        self.fill(self.sel("search_input"), term)
        self.click(self.sel("search_button"))

    def view_product(self, product_name: str) -> None:
        """Open the detail page of the product whose card carries `product_name`.

        Scopes to the card containing the name and clicks the View Product link
        inside it, rather than indexing across the family — the name and
        add-to-cart families are doubled per card, so an index taken from one
        would address the wrong element in another.
        """
        self.require_own_page()
        self.click_in_row(
            self.sel("product_cards"),
            product_name,
            self.sel("view_product_links"),
        )

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the listing is on screen. WAITS for it.

        Probes the All Products heading, which is present on the unsearched
        listing this method is used to confirm arrival at. (A searched view is
        confirmed separately via search_results_shown.)
        """
        return self.is_showing(self.sel("all_products_heading"), timeout_ms=timeout_ms)

    def search_results_shown(self) -> bool:
        """True once a search has actually EXECUTED. WAITS for it.

        Probes the Searched Products heading, which replaces the All Products
        heading only after a real term is entered and submitted. This is the
        only signal that distinguishes a one-result search from a search that
        never ran and still shows the full catalogue.

        Call this only where a search is expected to have run; it times out
        rather than returning False if none has.
        """
        return self.is_showing(self.sel("searched_products_heading"))

    def has_product_card(self, product_name: str) -> bool:
        """True once a result card for `product_name` is present. WAITS for it.

        Call this only where the product is expected to be found; it times out
        rather than returning False if the card never appears.
        """
        self.wait_for_row(self.sel("product_cards"), product_name, present=True)
        return True

    def get_result_count(self) -> int:
        """Number of product result cards currently rendered.

        A snapshot with no retry — use it only to READ the count, such as when
        asserting a no-match search rendered zero cards. The product_cards
        family is one element per card and is NOT doubled per card.
        """
        return self.get_count(self.sel("product_cards"))
