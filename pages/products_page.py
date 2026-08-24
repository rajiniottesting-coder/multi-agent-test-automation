"""
ProductsPage — the /products catalogue and search screen.

Selectors come from the app inventory (`pages.products`); this file never
contains a literal selector string. Set INVENTORY_PAGE, then look each element
up by its `elements` KEY via self.sel("<key>").

Search matches on product NAME and submits to the same page. A search that
matches nothing renders NO result cards rather than an empty-state message, so
absence is asserted by COUNTING cards, not by looking for text.

App: https://automationexercise.com
"""
from typing import List, Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class ProductsPage(BasePage):
    """The all-products listing and its search. Selectors: see `pages.products`
    in the app inventory.

    Several element families here match many elements at once, and two of them
    (product_names, add_to_cart_buttons) render TWICE per card. Read families
    with the plural helpers, and act on one product by scoping to the card that
    contains its name via click_in_row().
    """

    INVENTORY_PAGE = "products"

    # ── actions ──────────────────────────────────────────────
    def open_listing(self, base_url: str) -> None:
        """Navigate directly to the /products listing.

        Args:
            base_url: application base URL from the `base_url` fixture. The path
                      comes from the inventory, so it is never duplicated here.
        """
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.confirm_arrival()

    def search_for(self, term: str) -> None:
        """Enter a search term and submit it.

        Confirms it is ON this page first: filling a field that is not on
        screen does not fail fast — Playwright waits the full timeout and then
        blames the locator, which reads like a broken selector when the page is
        simply wrong. An empty term is a legitimate boundary case, so this
        method accepts and submits it as given.
        """
        self.require_own_page()
        self.fill(self.sel("search_input"), term)
        self.click(self.sel("search_button"))

    def open_product(self, product_name: str) -> None:
        """Open the detail page for the named product from the result cards.

        Scopes to the card that contains the product name, then clicks that
        card's View Product link. Scoping avoids the strict-mode violation
        that clicking the whole view_product_links family would raise, and it
        is robust to the per-card doubling of other families.
        """
        self.click_in_row(
            self.sel("product_cards"),
            product_name,
            self.sel("view_product_links"),
        )

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the products listing is on screen. WAITS for it.

        Probes the 'All Products' heading, which is present on the unsearched
        listing that open_listing() lands on. Delegates to is_showing() so a
        failed readiness check logs the selector, the wait and the URL rather
        than raising a bare assertion.
        """
        return self.is_showing(self.sel("all_products_heading"), timeout_ms=timeout_ms)

    def wait_for_search_executed(self) -> None:
        """Wait until a search has actually RUN.

        The 'Searched Products' heading replaces 'All Products' once a search
        executes. This is the only reliable signal that the search ran — a
        result count alone cannot distinguish 'the search returned one product'
        from 'the search never ran and the full catalogue is still shown'.
        Call this before asserting on results.
        """
        self.wait_visible(self.sel("searched_products_heading"))

    def get_result_names(self) -> List[str]:
        """Return every product name currently shown in the results.

        The product_names family renders twice per card, so a name may appear
        more than once here — assert containment ("Blue Top" in names), never
        an exact list.
        """
        return self.get_all_texts(self.sel("product_names"))

    def has_result(self, product_name: str) -> bool:
        """True once a result card for the named product is present. WAITS.

        Call this only where the product IS expected in the results. It times
        out if no such card ever appears, so do not use it to assert absence —
        use has_no_results() or get_result_card_count() for that.
        """
        self.wait_for_row(self.sel("product_cards"), product_name, present=True)
        return True

    def get_result_card_count(self) -> int:
        """Return the number of result cards currently shown.

        A snapshot with no waiting. Used to assert an empty result set: on this
        app a search matching nothing renders zero cards rather than an
        empty-state message, so counting cards is how absence is verified.
        """
        return self.get_count(self.sel("product_cards"))

    def has_no_results(self) -> bool:
        """True if the search returned no result cards right now. No waiting.

        The non-waiting probe for asserting an EMPTY result set. It reports the
        current state immediately, so a "returns no products" assertion is
        never blocked by a timeout the way a waiting reader would be.
        """
        return self.get_result_card_count() == 0
