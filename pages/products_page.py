"""
ProductsPage — the /products all-products listing and its search.

New page object for the shopping-session feature. Selectors come from the
`products` page in the app inventory; this file never contains a literal
selector — every element is looked up with self.sel("<key>").

Conventions (see pages/login_page.py for the worked reference):
  - business-verb method names that say WHAT they act on (search_for,
    open_product), never bare verbs
  - every method uses a BasePage helper; no raw self.page.* calls
  - no assertions here — those belong in step definitions
  - family selectors (product_cards, product_names, view_product_links,
    add_to_cart_buttons) are read with the plural helpers only, and a single
    member is acted on by scoping to the row that contains its text

App: https://automationexercise.com
"""
from typing import List

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class ProductsPage(BasePage):
    """All-products listing and product search.

    Selectors: see `pages.products` in the app inventory.

    Readiness: the inventory offers `all_products_heading` for the unsearched
    listing and `searched_products_heading` for the post-search state. There is
    no single element true in BOTH states — the search REPLACES one heading with
    the other — so is_loaded() probes the search box, which is present whether or
    not a search has run. (No `readiness` key is declared for this page.)
    """

    INVENTORY_PAGE = "products"

    # ── navigation ───────────────────────────────────────────
    def open_listing(self, base_url: str) -> None:
        """Navigate directly to the all-products listing."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.confirm_arrival()

    # ── actions ──────────────────────────────────────────────
    def search_for(self, term: str) -> None:
        """Type a search term into the search box and submit.

        This is the first action a scenario takes on the listing, so it
        confirms it is on this page before filling — a fill against a field
        that is not on screen waits the full timeout and then blames the
        locator rather than the wrong page.

        An empty term submits an empty box, which the app treats as "show the
        full catalogue"; that is a legitimate call, so no value check here.
        """
        self.require_own_page()
        self.fill(self.sel("search_input"), term)
        self.click(self.sel("search_button"))

    def open_product(self, name: str) -> None:
        """Open the product detail page for the card whose name is `name`.

        view_product_links is a per-card family (one link per product), so we
        scope to the card CONTAINING the product name rather than indexing a
        doubled family. click_in_row keeps the disambiguation inside BasePage.
        """
        self.click_in_row(
            self.sel("product_cards"),
            name,
            self.sel("view_product_links"),
        )

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self) -> bool:
        """True once the listing is on screen. WAITS for the search box.

        The search box survives both the unsearched and searched states, so it
        is a state-independent readiness signal where either heading would be
        true in only one state.
        """
        return self.is_showing(self.sel("search_input"))

    def search_has_executed(self) -> bool:
        """True once the 'Searched Products' heading is shown. WAITS for it.

        This is the only reliable signal that the search actually RAN — a card
        count alone cannot tell 'search returned one product' from 'search
        never ran and the page still shows the full catalogue'. Call this only
        where a search is expected to have executed.
        """
        return self.is_showing(self.sel("searched_products_heading"))

    def get_result_names(self) -> List[str]:
        """Visible product names currently listed, as a list of strings.

        product_names is a family (and doubled per card), so this returns each
        card's name — use it to assert a named product IS present via
        containment rather than indexing.
        """
        return self.get_all_texts(self.sel("product_names"))

    def get_result_count(self) -> int:
        """Number of product cards currently rendered — a SNAPSHOT, no wait.

        Reads product_cards, which is one-per-card and NOT doubled. Use this
        only to READ a number for logging or branching, never to assert on:
        an assertion on how many cards a search produced belongs in
        wait_for_result_count()/has_results()/has_no_results(), which retry.
        """
        return self.get_count(self.sel("product_cards"))

    def has_results(self) -> bool:
        """True once AT LEAST ONE product card is rendered. WAITS for one.

        Use this to assert a search returned the full catalogue: waits for the
        family to be non-empty, so it does not race the search request. It can
        only answer 'no' by exhausting its timeout, so call it only where
        results ARE expected.
        """
        self.wait_for_any(self.sel("product_cards"))
        return True

    def has_no_results(self) -> bool:
        """True once NO product cards are rendered. WAITS for the count to be 0.

        This app renders no empty-state message for a non-matching search, only
        zero cards, so absence is asserted by counting. A plain snapshot count
        would race the search request that clears the previous cards and could
        report the OLD catalogue as still present; wait_for_count retries until
        the family is empty and logs the reason it gave up. It can only answer
        'no' by timing out, so call it only where zero results ARE expected.
        Call search_has_executed() first to confirm the search actually ran.
        """
        self.wait_for_count(self.sel("product_cards"), 0)
        return True
