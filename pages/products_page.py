"""
ProductsPage — the All Products listing and search screen.

Selectors come from the app inventory (INVENTORY_PAGE = "products"); this file
never contains a literal selector string.

App: https://automationexercise.com
"""
from typing import List, Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class ProductsPage(BasePage):
    """All Products listing and search. Selectors: see `pages.products`.

    Search matches on product NAME and submits to the same page. Several of
    this page's families match many elements (product cards, product names,
    add-to-cart buttons, view-product links); read them with plural helpers
    and scope to one card when acting on a single product.
    """

    INVENTORY_PAGE = "products"

    # ── actions ──────────────────────────────────────────────
    def open_listing(self, base_url: str) -> None:
        """Navigate to the All Products listing.

        Args:
            base_url: application base URL, supplied by the `base_url` fixture.
                      The path comes from the inventory, so it is never
                      duplicated here.
        """
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.confirm_arrival()

    def search_for(self, term: str) -> None:
        """Type a search term and submit it.

        Confirms this page first: the search box is a field, and filling a
        field that is not on screen waits the full timeout and then blames the
        locator rather than the page.
        """
        self.require_own_page()
        self.fill(self.sel("search_input"), term)
        self.click(self.sel("search_button"))
        # Wait for the search to actually execute. The heading is the only
        # reliable signal it ran; a result count cannot distinguish a search
        # returning one product from a search that never ran.
        self.wait_visible(self.sel("searched_products_heading"))

    def open_product(self, product_name: str) -> None:
        """Open the detail page of the named product from the results.

        Scopes to the card containing the product name and clicks that card's
        View Product link, so the correct product opens even though the
        listing renders a whole family of such links.
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

        Probes the All Products heading, which is present on the unsearched
        listing that open_listing lands on.
        """
        return self.is_showing(self.sel("all_products_heading"), timeout_ms=timeout_ms)

    def search_executed(self, timeout_ms: Optional[int] = None) -> bool:
        """True once a search has run. WAITS for the Searched Products heading.

        Call this only when a search is expected to have executed. It is the
        reliable 'the search ran' signal — a result count alone cannot tell a
        one-product result from a page still showing the full catalogue.
        """
        return self.is_showing(self.sel("searched_products_heading"), timeout_ms=timeout_ms)

    def get_result_names(self) -> List[str]:
        """Every product name shown in the results, as a list of strings.

        Reads the product-name family with the plural helper. The family is
        rendered twice per card, so names may repeat; assert membership rather
        than an exact position.
        """
        return self.get_all_texts(self.sel("product_names"))

    def has_result(self, product_name: str) -> bool:
        """True if a result card for the named product is present.

        WAITS for at least one product card, then checks the names. Call this
        only when a match IS expected; for asserting NO results, use
        get_result_card_count() and assert it is zero.
        """
        self.wait_for_any(self.sel("product_cards"))
        return any(product_name in name for name in self.get_result_names())

    def get_result_card_count(self) -> int:
        """Number of product result cards currently displayed.

        A snapshot read, for asserting an empty result set: an empty search
        renders NO cards and NO 'no results' message, so counting cards is the
        only way to assert the empty case. Wait for the search to have executed
        (search_executed) before calling this, so the count reflects the search
        rather than a page still loading.
        """
        return self.get_count(self.sel("product_cards"))
