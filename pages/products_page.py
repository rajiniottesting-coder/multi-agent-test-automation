"""
ProductsPage — the /products listing and search screen.

Selectors: see `pages.products` in the app inventory. This page carries the
full catalogue, a search box, and per-card controls that are MULTI-MATCH by
design (product cards, names, add-to-cart buttons and View Product links each
repeat once per product, and some repeat twice per card). Methods here read
those families with plural accessors and scope to a single card by product
name; they never click a family as a whole.

Reaching /products by clicking the top-nav Products link is the NavPage's job,
not this page object's — that link belongs to inventory page 'nav', and a page
object may only resolve keys from its OWN page. The step definition drives the
nav via NavPage and then confirms arrival with this page's readiness reader.

App: https://automationexercise.com
"""
from typing import List, Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class ProductsPage(BasePage):
    """The all-products listing and search page."""

    INVENTORY_PAGE = "products"

    # ── actions ──────────────────────────────────────────────
    def open_listing(self, base_url: str) -> None:
        """Navigate directly to the /products listing and confirm arrival."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.confirm_arrival()

    def search_for(self, term: str) -> None:
        """Type a search term and submit it.

        Fills as its opening action, so it makes sure it is on this page first;
        filling a field that is not on screen would wait the full timeout and
        then blame the locator.
        """
        self.require_own_page()
        self.fill(self.sel("search_input"), term)
        self.click(self.sel("search_button"))

    def view_product(self, name: str) -> None:
        """Open the product whose card contains `name` via its View Product link.

        Scopes to the card containing the product name rather than indexing
        across the doubled families. The destination is the product detail
        page, whose own page object confirms arrival separately.
        """
        self.click_in_row(
            self.sel("product_cards"),
            name,
            self.sel("view_product_links"),
        )

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the all-products listing heading is on screen. WAITS for it.

        Call this only where the unsearched listing is the expected state; it
        can answer 'no' only by exhausting its timeout. After a search has run
        this heading is replaced, so use is_search_results_shown() instead.
        """
        return self.is_showing(self.sel("all_products_heading"), timeout_ms=timeout_ms)

    def is_search_results_shown(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the 'Searched Products' heading is on screen. WAITS for it.

        This heading is the only reliable signal that a search actually
        EXECUTED — a card count alone cannot distinguish 'search returned one'
        from 'search never ran'. Call this only where a search result is the
        expected state; it can answer 'no' only by timing out.
        """
        return self.is_showing(
            self.sel("searched_products_heading"), timeout_ms=timeout_ms
        )

    def get_product_names(self) -> List[str]:
        """Every product name currently rendered, as a list of strings.

        The name family is doubled per card, so a name may appear more than
        once — assert containment, not exact membership counts.
        """
        return self.get_all_texts(self.sel("product_names"))

    def has_product(self, name: str) -> bool:
        """True once a result card containing `name` is present. WAITS for it.

        Call this only where the product is EXPECTED to be listed; it can
        answer 'no' only by exhausting its timeout.
        """
        self.wait_for_row(self.sel("product_cards"), name, present=True)
        return True

    def get_result_count(self) -> int:
        """Number of product result cards rendered right now (no waiting).

        Reads the non-doubled product-card family, so this is a true card
        count. For an empty search this page renders zero cards and NO
        empty-state message, so counting cards is the only way to assert
        absence — assert this equals 0 for a no-match search.
        """
        return self.get_count(self.sel("product_cards"))
