"""
ProductsPage — the /products listing and search screen.

New page object for the shopping-session feature. Selectors come from the
`products` page in the app inventory; this file never contains a literal
selector string.

Conventions (mirrors pages/login_page.py):
  - INVENTORY_PAGE names the inventory page; self.sel("<key>") resolves keys.
  - methods are business verbs that say WHAT they act on.
  - readiness probes the state-independent search_input (see is_loaded).
  - family selectors (product_names, view_product_links) are read with the
    plural helpers or scoped with click_in_row; never clicked directly.

App: https://automationexercise.com
"""
from typing import List, Optional

from pages.base_page import BasePage


class ProductsPage(BasePage):
    """Product listing and search. Selectors: see `products` in the inventory.

    The listing has two mutually-exclusive headings — 'All Products' before a
    search and 'Searched Products' after one — so neither is a reliable
    readiness signal. The search input is present in every state, so is_loaded
    probes that.
    """

    INVENTORY_PAGE = "products"

    # ── navigation / readiness ───────────────────────────────
    def confirm_arrival(self, **params: object) -> None:
        """Confirm the browser reached /products; recover if an ad ate the nav.

        Overrides BasePage.confirm_arrival to also wait for the search input,
        so callers landing here from NavPage.open_products() get a page that is
        actually interactive.
        """
        super().confirm_arrival(**params)
        self.wait_visible(self.sel("search_input"))

    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the products page is interactive. WAITS for it.

        Probes the search input, which is present both before and after a
        search — unlike the two headings, each of which is true in only one of
        those states.
        """
        return self.is_showing(self.sel("search_input"), timeout_ms=timeout_ms)

    # ── actions ──────────────────────────────────────────────
    def search_for(self, term: str) -> None:
        """Type a search term and submit it.

        Search matches on product NAME and submits back to /products. After
        this, assert has_searched() before reading results — a result count
        alone cannot distinguish 'search returned one product' from 'search
        never ran and the full catalogue is still shown'.
        """
        self.fill(self.sel("search_input"), term)
        self.click(self.sel("search_button"))

    def open_product(self, product_name: str) -> None:
        """Open the detail page for the product whose card contains the name.

        Scopes to the card containing the name and clicks its View Product
        link, rather than indexing into the doubled name/button families.
        """
        self.click_in_row(
            self.sel("product_cards"),
            product_name,
            self.sel("view_product_links"),
        )

    # ── queries ──────────────────────────────────────────────
    def has_searched(self) -> bool:
        """True once the 'Searched Products' heading is on screen. WAITS.

        The only reliable signal that a search actually EXECUTED. Assert this
        before asserting on the result set.
        """
        return self.is_showing(self.sel("searched_products_heading"))

    def get_result_names(self) -> List[str]:
        """Every product name currently shown, in DOM order.

        The name family is doubled (once per card, once in the hover overlay),
        so a name may appear twice — use containment, not an exact list, when
        asserting a product is present.
        """
        return self.get_all_texts(self.sel("product_names"))

    def has_product(self, product_name: str) -> bool:
        """True if a card for the named product is present in the results."""
        return any(product_name in name for name in self.get_result_names())

    def get_result_card_count(self) -> int:
        """Number of result cards currently shown (no waiting).

        product_cards is one-per-card and NOT doubled, so this is the honest
        card count. Used to assert the empty-result case: a search matching
        nothing renders no cards and no empty-state message, so absence is
        asserted by counting cards, not by looking for text.
        """
        return self.get_count(self.sel("product_cards"))

    def has_no_results(self) -> bool:
        """True if the search produced zero result cards."""
        return self.get_result_card_count() == 0
