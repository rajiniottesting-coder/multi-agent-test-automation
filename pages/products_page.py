"""
ProductsPage — the /products listing and its search behaviour.

New page object for the shopping-session and search scenarios. Follows the
conventions of pages/login_page.py:

  - SELECTORS COME FROM THE APP INVENTORY. Set INVENTORY_PAGE, then use
    self.sel("<element_key>"). Never a literal selector string here.
  - methods are business verbs that say WHAT they act on (search_for,
    open_product_detail), not UI mechanics.
  - every method uses a BasePage helper; no raw self.page.* calls.
  - no assertions here — those belong in step definitions.
  - waiting predicates (is_*, has_*) are built on waiting probes; the
    non-waiting probe is reserved for asserting ABSENCE.

App: https://automationexercise.com
"""
from typing import List, Optional

from pages.base_page import BasePage


class ProductsPage(BasePage):
    """The All Products listing and its search results.

    Selectors: see `pages.products` in the app inventory.

    STATE-DEPENDENT HEADINGS. `all_products_heading` shows on the unsearched
    listing; `searched_products_heading` replaces it once a search has run.
    A readiness probe must survive both states, so is_loaded() probes the
    search input, which is present in every state of this page.
    """

    INVENTORY_PAGE = "products"

    # ── actions ──────────────────────────────────────────────
    def open_listing(self, base_url: str) -> None:
        """Navigate directly to the All Products listing."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    def search_for(self, term: str) -> None:
        """Type a term into the search box and submit the search.

        Search matches on product NAME and submits back to /products, so the
        page reloads in its 'Searched Products' state.
        """
        self.fill(self.sel("search_input"), term)
        self.click(self.sel("search_button"))

    def open_product_detail(self, product_name: str) -> None:
        """Open the product detail page for the card carrying `product_name`.

        Scopes to the card containing the name and clicks its View Product
        link, so the correct product's id is followed — the test never invents
        an id.
        """
        self.click_in_row(
            self.sel("product_cards"),
            product_name,
            self.sel("view_product_links"),
        )

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the products page is on screen. WAITS for it.

        Probes the search input, the one control present in EVERY state of this
        page — before a search, after a matching search and after an empty
        search alike. The two headings each hold in only one state, so neither
        is a safe readiness signal.
        """
        return self.is_showing(self.sel("search_input"), timeout_ms=timeout_ms)

    def search_executed(self, timeout_ms: Optional[int] = None) -> bool:
        """True once a search has run. WAITS for the Searched Products heading.

        This heading appearing is the only reliable signal that the search
        EXECUTED — a result count alone cannot tell 'the search returned one
        product' from 'the search never ran and the full catalogue is shown'.
        Call this only when a search is expected to have run.
        """
        return self.is_showing(
            self.sel("searched_products_heading"), timeout_ms=timeout_ms
        )

    def get_result_names(self) -> List[str]:
        """Every product name in the results, in DOM order.

        The name family renders twice per card (card plus hover overlay), so
        this list contains duplicates. Use containment checks rather than
        length for presence — assert_result_count() is the right tool for
        counting cards.
        """
        return self.get_all_texts(self.sel("product_names"))

    def has_product(self, product_name: str) -> bool:
        """True once a card for `product_name` is in the results. WAITS.

        Built on wait_for_row, so it re-checks until the timeout right after a
        search when the results are still settling. Call this only when the
        product IS expected to be present; it can only answer 'no' by timing
        out.
        """
        try:
            self.wait_for_row(self.sel("product_cards"), product_name, present=True)
            return True
        except Exception:
            return False

    def assert_result_count(self, expected: int) -> None:
        """Wait until exactly `expected` result cards are shown.

        Counts the card family (one per card, NOT doubled). Uses wait_for_count
        so it settles after the search reload rather than snapshotting a
        stale count. For the empty case pass 0 — this app renders no
        empty-state message, so the card count is the signal.
        """
        self.wait_for_count(self.sel("product_cards"), expected)
