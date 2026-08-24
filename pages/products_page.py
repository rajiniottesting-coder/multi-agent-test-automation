"""
ProductsPage — the /products all-products listing and search results.

Selectors come from `pages.products` in the app inventory; this file never
holds a literal selector. Methods are business verbs that name what they act
on, per the naming rule.

App: https://automationexercise.com
"""
from typing import Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class ProductsPage(BasePage):
    """All-products listing and search results.

    Selectors: see `pages.products` in the app inventory.

    Search and result-card families are MULTI-MATCH by design (product_cards,
    product_names, view_product_links). They are read with plural helpers and
    scoped by row text to act on one member — never clicked as a family.
    """

    INVENTORY_PAGE = "products"

    # ── actions ──────────────────────────────────────────────
    def open_products(self, base_url: str) -> None:
        """Navigate directly to the all-products listing page."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.confirm_arrival()

    def search_for(self, term: str) -> None:
        """Type a search term and submit.

        Confirms it is on this page first: filling a field that is not on
        screen does not fail fast — Playwright waits the full timeout and then
        blames the locator, which reads like a broken selector when the page is
        simply wrong.
        """
        self.require_own_page()
        self.fill(self.sel("search_input"), term)
        self.click(self.sel("search_button"))

    def open_product_from_results(self, product_name: str) -> None:
        """Open the detail page for the named product from the result cards.

        Scopes to the card CONTAINING the product name, then clicks its View
        Product link — never an index across the doubled families. product_cards
        is one-per-card (not doubled), so it is the safe row family to scope on.
        """
        self.click_in_row(
            self.sel("product_cards"),
            product_name,
            self.sel("view_product_links"),
        )

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the all-products listing is on screen. WAITS for it.

        Probes the 'All Products' heading, which is present on the unsearched
        listing — the natural readiness signal when arriving at /products.
        """
        return self.is_showing(self.sel("all_products_heading"), timeout_ms=timeout_ms)

    def search_has_executed(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the search has actually run. WAITS for it.

        Asserts on the 'Searched Products' heading, which REPLACES the All
        Products heading after a search submits. A result count alone cannot
        distinguish 'search returned one product' from 'search never ran and
        the full catalogue is still shown', so callers should confirm this
        before reading results. Call only where a search is expected to have
        run; it times out otherwise.
        """
        return self.is_showing(self.sel("searched_products_heading"), timeout_ms=timeout_ms)

    def get_result_product_names(self) -> list[str]:
        """Every product name shown among the results, as a list of strings.

        Reads the MULTI-MATCH product_names family with get_all_texts(). Names
        are doubled per card (card + hover overlay), so callers should assert
        containment rather than rely on the count of this list.
        """
        return self.get_all_texts(self.sel("product_names"))

    def results_include(self, product_name: str) -> bool:
        """True if the named product appears among the result cards.

        WAITS for at least one result card to render before checking, so it does
        not race the search request. Membership check against the names family.
        """
        self.wait_for_any(self.sel("product_cards"))
        return any(product_name in name for name in self.get_result_product_names())

    def get_result_card_count(self) -> int:
        """Number of result cards currently shown (no waiting).

        Uses product_cards, which is one-per-card and NOT doubled. Read-only —
        for asserting an EMPTY result set use has_no_results(), which WAITS for
        the family to empty rather than snapshotting the count once.
        """
        return self.get_count(self.sel("product_cards"))

    def has_no_results(self) -> bool:
        """True when a search returned zero product cards. WAITS for the state.

        Call this only where an empty result set is the expected answer; it
        WAITS and times out if cards ARE present. The site renders NO
        empty-state text for a no-match search, so absence is verified against
        the product_cards family.

        First confirms the search actually executed (searched_products_heading),
        which WAITS — this distinguishes 'search ran and matched nothing' from
        'search never ran'. Then wait_for_any(..., present=False) retries until
        the card family is empty and logs the reason it gave up, rather than
        reading the count once and racing the search request.
        """
        self.wait_visible(self.sel("searched_products_heading"))
        self.wait_for_any(self.sel("product_cards"), present=False)
        return True
