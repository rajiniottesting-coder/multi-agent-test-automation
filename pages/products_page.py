"""
ProductsPage — the /products catalogue and search screen.

Selectors come from the app inventory (see `pages.products`). Set
INVENTORY_PAGE and look each element up with self.sel("<key>"); never write a
literal selector here.

Search on this site submits to the SAME page and swaps the heading:
'All Products' becomes 'Searched Products'. That heading swap is the only
reliable signal that the search actually EXECUTED — a card count alone cannot
distinguish 'search returned one product' from 'search never ran and the full
catalogue is still showing'. So assert on the searched heading before asserting
on results.

An empty / non-matching search renders NO result cards and NO empty-state
message, so absence is asserted by counting cards.

App: https://automationexercise.com
"""
import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class ProductsPage(BasePage):
    """/products listing, search and view-product navigation.

    Selectors: see `pages.products` in the app inventory. Several element keys
    (product_cards, product_names, view_product_links) are MULTI-MATCH — read
    them with the plural helpers, and scope to a single card by its text when
    acting on one member.
    """

    INVENTORY_PAGE = "products"

    # ── actions ──────────────────────────────────────────────
    def open_listing(self, base_url: str) -> None:
        """Navigate directly to the /products catalogue by URL."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.confirm_arrival()

    def go_to_products(self) -> None:
        """Reach /products by clicking the top-nav Products link.

        Confirms arrival: a click is not a guaranteed navigation on this site
        (an ad interstitial can consume the first navigation after a load), so
        the destination page object re-issues the navigation if the browser
        did not move.
        """
        self.confirm_arrival()

    def search_for(self, term: str) -> None:
        """Type a search term and submit it.

        This is the first action, so it confirms the browser is on this page
        before filling — filling a field that is not on screen does not fail
        fast, it burns the full timeout and then blames the field.

        The term may be empty (an empty-search edge case); fill() clears the
        field first, so an empty value submits a blank search rather than
        re-running the previous one.
        """
        self.require_own_page()
        self.fill(self.sel("search_input"), term)
        self.click(self.sel("search_button"))

    def open_product(self, product_name: str) -> None:
        """Open the detail page for the named product from the result cards.

        product_names and view_product_links are BOTH families, but they do
        NOT run in lockstep here — product_names is doubled per card (rendered
        once in the card and once in the hover overlay) while product_cards is
        not. So an index taken from the names family cannot be applied to the
        links family. Scope to the card CONTAINING the name and click the
        View Product link inside it instead.
        """
        self.require_own_page()
        self.click_in_row(
            self.sel("product_cards"),
            product_name,
            self.sel("view_product_links"),
        )

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self) -> bool:
        """True once the catalogue's stable heading is on screen. WAITS.

        Uses the 'All Products' heading, which is present on the unsearched
        listing that open_listing / go_to_products land on. Do not use it after
        a search — a search replaces it with the 'Searched Products' heading.
        """
        return self.is_showing(self.sel("all_products_heading"))

    def has_searched(self) -> bool:
        """True once a search has EXECUTED. WAITS, and times out if it has not.

        The 'Searched Products' heading replaces 'All Products' only after the
        search runs, so this is the reliable 'the search actually happened'
        signal. Call it only where a search is expected; asserting the search
        did NOT run this way would time out rather than return False.
        """
        return self.is_showing(self.sel("searched_products_heading"))

    def has_product(self, product_name: str) -> bool:
        """True once a result card for the named product is present. WAITS.

        Call this only where the product IS expected among the results —
        wait_for_row re-checks until the timeout and would time out if the
        product never appears.
        """
        self.wait_for_row(self.sel("product_cards"), product_name, present=True)
        return True

    def get_result_names(self) -> list[str]:
        """Every result card's product name as a list of strings.

        product_names is a MULTI-MATCH family (and doubled per card), so this
        may contain duplicates. Use it to check membership, not for an exact
        count — use get_result_count() for counting.
        """
        return self.get_all_texts(self.sel("product_names"))

    def get_result_count(self) -> int:
        """Number of result CARDS currently rendered.

        Reads product_cards, which is one element per card and NOT doubled, so
        it is the right family to count. A snapshot with no wait — appropriate
        here because the empty-search / no-match case renders zero cards and
        there is nothing to wait for.
        """
        return self.get_count(self.sel("product_cards"))
