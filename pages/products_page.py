"""
ProductsPage — the /products listing and its search.

Selectors come from the app inventory (INVENTORY_PAGE = "products"); this file
never contains a literal selector. Methods are business verbs that name what
they act on. Assertions belong in step definitions, not here.

App: https://automationexercise.com
"""
from typing import List

from pages.base_page import BasePage


class ProductsPage(BasePage):
    """Product listing and search. Selectors: see `pages.products` inventory.

    Several families here are MULTI-MATCH and some are DOUBLED per card
    (product_names, add_to_cart_buttons render twice per card). Read them with
    the plural helpers; act on one member by scoping to the card that contains
    its name via click_in_row().
    """

    INVENTORY_PAGE = "products"

    # ── navigation ───────────────────────────────────────────
    def open_listing(self, base_url: str) -> None:
        """Navigate directly to the product listing and confirm arrival."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.confirm_arrival()

    def is_loaded(self) -> bool:
        """True once the listing is on screen. WAITS for it.

        Probes the All Products heading, which is present on the freshly
        loaded, unsearched listing — the state open_listing() lands in.
        """
        return self.is_showing(self.sel("all_products_heading"))

    # ── search ───────────────────────────────────────────────
    def search_for(self, term: str) -> None:
        """Type a search term and submit it, staying on /products."""
        self.fill(self.sel("search_input"), term)
        self.click(self.sel("search_button"))

    def wait_for_search_results(self) -> None:
        """Wait until the search has actually executed.

        The Searched Products heading replaces All Products only after a search
        runs, so it is the one reliable signal that the results shown belong to
        the query rather than to the full catalogue.
        """
        self.wait_visible(self.sel("searched_products_heading"))

    def search_has_executed(self) -> bool:
        """True once the search has run. WAITS for the Searched Products heading.

        Call only where a search IS expected to have executed; it can answer
        'no' only by timing out.
        """
        return self.is_showing(self.sel("searched_products_heading"))

    # ── results ──────────────────────────────────────────────
    def get_result_count(self) -> int:
        """Number of product cards currently rendered in the results.

        Snapshot with no wait — use for reading a count, not for asserting one
        settles. product_cards is one-per-card (not doubled).
        """
        return self.get_count(self.sel("product_cards"))

    def has_no_results(self) -> bool:
        """True once the results area holds zero product cards. WAITS.

        An empty search on this app renders NO cards and NO empty-state text,
        so absence is asserted by waiting for the card count to settle at zero.
        Built on wait_for_count, which retries until the timeout and logs the
        reason it gave up, rather than snapshotting the count once. Call only
        where the empty result IS the expected answer.
        """
        try:
            self.wait_for_count(self.sel("product_cards"), 0)
            return True
        except Exception:
            return False

    def has_product(self, product_name: str) -> bool:
        """True once a result card containing `product_name` is present. WAITS.

        Built on wait_for_row so a step asserting a product appeared does not
        race the search reload. Call only where the product IS expected.
        """
        try:
            self.wait_for_row(self.sel("product_cards"), product_name, present=True)
            return True
        except Exception:
            return False

    # ── navigation to a product ──────────────────────────────
    def open_product(self, product_name: str) -> None:
        """Click the View Product link on the card for `product_name`.

        Scopes to the card containing the name and clicks the View Product
        link inside it — view_product_links is a per-card family and must not
        be clicked as a whole.
        """
        self.click_in_row(
            self.sel("product_cards"),
            product_name,
            self.sel("view_product_links"),
        )
