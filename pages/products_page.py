"""
ProductsPage — the /products listing and search screen.

Selectors: see `pages.products` in the app inventory. This page carries TWO
signals that a search actually executed: `searched_products_heading` appears
and `all_products_heading` disappears. A result count alone cannot distinguish
"the search returned one product" from "the search never ran". Assert on the
heading first.

Several families on this page (product cards, names, add-to-cart buttons, view
product links) match many elements, and product_names / add_to_cart_buttons are
DOUBLED per card. Never index across those. To act on one product, scope to the
card containing its text, or open it via its View Product link.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class ProductsPage(BasePage):
    """The all-products listing and search page."""

    INVENTORY_PAGE = "products"

    # ── actions ──────────────────────────────────────────────
    def open_listing(self, base_url: str) -> None:
        """Navigate to the all-products listing page."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.confirm_arrival()

    def search_for(self, term: str) -> None:
        """Type a search term and submit it.

        Search matches on product NAME and submits to this same page. After
        this returns, use has_searched() to confirm the search executed before
        asserting on results.
        """
        self.fill(self.sel("search_input"), term)
        self.click(self.sel("search_button"))

    def open_product(self, product_name: str) -> None:
        """Open the detail page for the product whose card contains `product_name`.

        Scopes to the card containing the name and clicks its View Product
        link, rather than indexing into the multi-match link family — the link
        family and the name family are not guaranteed to run in lockstep on
        this page (names are doubled per card).
        """
        self.click_in_row(
            self.sel("product_cards"),
            product_name,
            self.sel("view_product_links"),
        )

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the listing page has loaded. WAITS for it.

        Probes the search input, which is present on both the unsearched
        catalogue and the searched-results state — unlike the All Products
        heading, which a search replaces.
        """
        return self.is_showing(self.sel("search_input"), timeout_ms=timeout_ms)

    def has_searched(self) -> bool:
        """True once a search has executed. WAITS for the searched heading.

        The reliable signal that the search RAN — a result count alone cannot
        tell an empty result from an un-run search. Call this only where a
        search is expected to have executed; it waits and times out otherwise.
        """
        return self.is_showing(self.sel("searched_products_heading"))

    def get_result_count(self) -> int:
        """Number of product result cards currently rendered.

        A search matching nothing renders ZERO cards rather than an empty-state
        message (per the inventory), so absence of results is asserted by this
        count being 0. Not a waiting reader: call it only after has_searched()
        has confirmed the search executed.
        """
        return self.get_count(self.sel("product_cards"))

    def has_result_for(self, product_name: str) -> bool:
        """True once a result card containing `product_name` is present. WAITS.

        The name family is a multi-match blob doubled per card, so this scopes
        to the CARD family and waits for the one containing the product name.
        Call this only where the product is expected to appear — it waits and
        times out otherwise. To assert a search returned NOTHING, use
        get_result_count() == 0 instead.
        """
        self.wait_for_row(self.sel("product_cards"), product_name, present=True)
        return True
