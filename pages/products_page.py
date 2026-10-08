"""
ProductsPage — the /products listing and search screen.

Selectors come from the `products` page in the app inventory; this file never
holds a literal selector. See pages/login_page.py for the conventions this
page object follows.

App: https://automationexercise.com
"""
from typing import Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class ProductsPage(BasePage):
    """Products listing and search. Selectors: see `products` in the inventory.

    The product-card families (cards, names, add-to-cart buttons, view-product
    links) are MULTI-MATCH and some are doubled per card, so this page object
    never clicks a family member directly - it scopes to the card that contains
    the product name, or opens a product by clicking its unique View Product
    link.
    """

    INVENTORY_PAGE = "products"

    # ── actions ──────────────────────────────────────────────
    def open_listing(self, base_url: str) -> None:
        """Navigate directly to the /products listing page."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.confirm_arrival()

    def search_for(self, term: str) -> None:
        """Type a search term and submit it.

        Confirms it is on this page before filling: a fill that is the first
        action on a page not yet reached does not fail fast - Playwright waits
        the full timeout and then blames the field rather than the wrong page.
        """
        self.require_own_page()
        self.fill(self.sel("search_input"), term)
        self.click(self.sel("search_button"))

    def open_product(self, product_name: str) -> None:
        """Open the detail page for the product whose card contains `product_name`.

        Scopes to the card containing the name and clicks its View Product link
        from inside that card, rather than indexing into the MULTI-MATCH link
        family - the name and button families are doubled per card, so an index
        taken from one does not address the right element in another.
        """
        self.click_in_row(
            self.sel("product_cards"),
            product_name,
            self.sel("view_product_links"),
        )

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the products listing is on screen. WAITS for it.

        Probes the All Products heading, which is present on the unsearched
        listing. (The search-executed state swaps it for 'Searched Products';
        use search_results_shown() to confirm a search actually ran.)
        """
        return self.is_showing(self.sel("all_products_heading"), timeout_ms=timeout_ms)

    def search_results_shown(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the 'Searched Products' heading is shown. WAITS for it.

        Call this only where a search is expected to have RUN. An empty query
        does not run a search and leaves the All Products heading in place, so
        this reader would time out for that case - which is the correct answer
        for 'did the search execute', but means it must not be used to branch.
        """
        return self.is_showing(self.sel("searched_products_heading"), timeout_ms=timeout_ms)

    def get_result_names(self) -> list[str]:
        """Return the visible names of all product result cards.

        The name family is doubled per card, so a name present in the catalogue
        appears more than once here. Callers assert containment, not counts.
        """
        return self.get_all_texts(self.sel("product_names"))

    def result_includes(self, product_name: str) -> bool:
        """True once a result card for `product_name` is shown. WAITS for it.

        Built on wait_for_row, which re-checks until the timeout, so it is safe
        to call immediately after submitting a search. Use only where the
        product IS expected; to assert a term matches nothing, use
        has_no_result_cards(), which does not wait.
        """
        self.wait_for_row(self.sel("product_cards"), product_name, present=True)
        return True

    def has_no_result_cards(self) -> bool:
        """True if no product result cards are displayed right now.

        An empty search on this site renders NO cards and NO 'no results'
        message, so absence is asserted by counting cards. This is the
        non-waiting probe for that absence case - it returns at once and never
        raises, so it can be negated or checked directly without paying a
        timeout for the expected-empty answer. It first waits for the search to
        have executed (the 'Searched Products' heading) so the count is read
        after the listing has settled, not while the full catalogue is still
        on screen.
        """
        self.wait_visible(self.sel("searched_products_heading"))
        return self.get_count(self.sel("product_cards")) == 0
