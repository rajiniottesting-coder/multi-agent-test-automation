"""
ProductsPage — the All Products listing and its search box.

Selectors come from the `products` page in the app inventory. This page object
exposes search, result-heading checks, product-name presence and View Product
navigation. It never contains a literal selector string: every element is
resolved through self.sel("<key>").

App: https://automationexercise.com
"""
from typing import Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class ProductsPage(BasePage):
    """All Products listing. Selectors: see `products` in the app inventory.

    Two families here are DOUBLED per card (each card renders its name and its
    Add-to-cart control twice, once in the card and once in the hover overlay),
    so an index from one family is not valid in another. This page reads names
    as a set with get_all_texts() and reaches a product's detail page by
    scoping to the card that contains its name, never by indexing.
    """

    INVENTORY_PAGE = "products"

    # ── actions ──────────────────────────────────────────────
    def open_listing(self, base_url: str) -> None:
        """Navigate to the All Products listing.

        Args:
            base_url: application base URL from the `base_url` fixture. The path
                      comes from the inventory, so it is never duplicated here.
        """
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    def search_for(self, term: str) -> None:
        """Type a term into the search box and submit.

        Confirms it is ON this page first. Filling a field that is not on
        screen does not fail fast — Playwright waits the full timeout and then
        blames the locator, which reads like a broken selector when the page is
        simply wrong.
        """
        self.require_own_page()
        self.fill(self.sel("search_input"), term)
        self.click(self.sel("search_button"))

    def submit_empty_search(self) -> None:
        """Clear the search box and submit with no term.

        The inventory documents that an empty submit does NOT run a search:
        the full catalogue stays on screen and the All Products heading
        remains. This method makes that behaviour explicit for its scenario.
        """
        self.require_own_page()
        self.clear(self.sel("search_input"))
        self.click(self.sel("search_button"))

    def view_product(self, product_name: str) -> None:
        """Open the detail page for the card whose text is `product_name`.

        Scopes to the card containing the name rather than indexing into a
        doubled family. Clicks the View Product link inside that card, which
        navigates to the product's detail page.
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

        Probes the search box, which is present in every state of this page —
        on the unsearched listing, after a search that returned results, and
        after one that returned none. The All Products heading is replaced by
        the Searched Products heading once a search runs, so it cannot be the
        readiness signal.
        """
        return self.is_showing(self.sel("search_input"), timeout_ms=timeout_ms)

    def get_product_names(self) -> list[str]:
        """Every product name currently rendered, as a list of strings.

        The name family is doubled per card, so a product present once appears
        twice here. Callers should assert containment, not an exact count.
        """
        return self.get_all_texts(self.sel("product_names"))

    def has_product(self, product_name: str) -> bool:
        """True once a card whose text contains `product_name` is present.

        WAITS for the card, so call this only where presence is the expected
        answer. It scopes to the card family (one member per card, NOT doubled)
        so the wait is on a real result rather than an overlay duplicate.
        """
        self.wait_for_row(self.sel("product_cards"), product_name, present=True)
        return True

    def get_result_count(self) -> int:
        """Number of product result CARDS currently rendered.

        Reads the card family (one per card, not doubled), so this is the true
        number of results. An empty search term does NOT run a search, so this
        returns the full catalogue count in that case; a genuinely
        non-matching term returns zero. Use this to assert an empty result set,
        which this site renders as zero cards with no 'no results' message.
        """
        return self.get_count(self.sel("product_cards"))

    def has_all_products_heading(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the 'All Products' heading is on screen. WAITS for it.

        This heading stays in place for an EMPTY search submit, which never
        runs a search, so it is the reliable signal that the browser is still
        on the unsearched listing. Call this only where the heading is the
        expected state.
        """
        return self.is_showing(self.sel("all_products_heading"), timeout_ms=timeout_ms)

    def has_searched_products_heading(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the 'Searched Products' heading is on screen. WAITS.

        This heading replaces the All Products heading only after a real search
        (a term entered and submitted) has executed. It is the only reliable
        signal that a search RAN, as distinct from the full catalogue still
        being shown. Call this only where a search is expected to have run.
        """
        return self.is_showing(
            self.sel("searched_products_heading"), timeout_ms=timeout_ms
        )
