"""
ProductsPage — the /products all-products listing and its search.

Selectors come from the app inventory (`products` page). This page carries
several FAMILY selectors (product_cards, product_names, view_product_links,
add_to_cart_buttons) — some of which the inventory notes are DOUBLED per card.
Never act on a family directly; scope to the card containing the product name.

The listing's own readiness signal is complicated by search: the "All Products"
heading is REPLACED by "Searched Products" once a search runs, so neither
heading survives every state. The search box, by contrast, is present on the
unsearched listing and on every search result, so it is the state-independent
readiness element used by is_loaded().

App: https://automationexercise.com
"""
from typing import Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class ProductsPage(BasePage):
    """All-products listing and product search.

    Selectors: see `pages.products` in the app inventory.
    """

    INVENTORY_PAGE = "products"

    # ── actions ──────────────────────────────────────────────
    def open_listing(self, base_url: str) -> None:
        """Navigate directly to the /products listing."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.confirm_arrival()

    def search_for(self, term: str) -> None:
        """Type a search term into the search box and submit.

        Confirms it is on this page first: filling a field that is not on
        screen does not fail fast, it burns the full Playwright timeout and
        then blames the locator. An empty term is legal here — the app treats
        an empty search as 'show the full catalogue'.
        """
        self.require_own_page()
        self.fill(self.sel("search_input"), term)
        self.click(self.sel("search_button"))

    def open_product(self, product_name: str) -> None:
        """Open a product's detail page via its 'View Product' link.

        view_product_links is a family (one per card) matched by href prefix,
        so this scopes to the card CONTAINING the product name rather than
        indexing across a doubled family. Ends by confirming we left the
        listing is NOT this page object's job — the detail page object confirms
        its own arrival.
        """
        self.click_in_row(
            self.sel("product_cards"),
            product_name,
            self.sel("view_product_links"),
        )

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the products listing is on screen. WAITS for it.

        Probes the search box: it is the readiness element that survives every
        state this page can be in (unsearched listing AND search results),
        unlike either heading, which each exist in only one state.
        """
        return self.is_showing(self.sel("search_input"), timeout_ms=timeout_ms)

    def get_product_names(self) -> list[str]:
        """Every visible product name on the listing, as a list of strings.

        product_names is a family (and doubled per card), so this reads them
        all rather than indexing. Callers assert membership, not position.
        """
        return self.get_all_texts(self.sel("product_names"))

    def search_results_include(self, product_name: str) -> bool:
        """True once a card whose name contains `product_name` is present.

        WAITS: uses wait_for_row against the card family so the assertion does
        not race the search request. Call this only where the product IS
        expected to be found — for the not-found case, use has_any_result_cards.
        """
        self.wait_for_row(self.sel("product_cards"), product_name, present=True)
        return True

    def has_any_result_cards(self) -> bool:
        """True if AT LEAST ONE product card is showing. WAITS for one.

        For asserting that a search returned SOMETHING (e.g. the full catalogue
        after an empty query). Do not negate this — negating a waiting probe
        pays the full timeout on every pass. To assert NO cards, use
        get_result_count() == 0, which does not wait for rows that will never
        appear.
        """
        self.wait_for_any(self.sel("product_cards"), present=True)
        return True

    def get_result_count(self) -> int:
        """Number of product cards currently rendered (no waiting).

        A non-matching search renders zero cards and NO empty-state message
        (see inventory _empty_search note), so absence is asserted by counting
        cards, not by looking for text. Use this for the zero-result case; use
        has_any_result_cards() for the 'there are some' case.
        """
        return self.get_count(self.sel("product_cards"))
