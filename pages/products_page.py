"""
ProductsPage — the All Products / search screen.

Selectors come from the app inventory (page key "products"); this file never
writes a literal selector. See pages/login_page.py for the conventions this
follows.

App: https://automationexercise.com
"""
from typing import List

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class ProductsPage(BasePage):
    """All Products listing and product search.

    Selectors: see `products` in the app inventory. Several keys are families
    (product_cards, product_names, view_product_links, add_to_cart_buttons) —
    read them with the plural helpers, and act on one member by scoping to the
    card that contains the product name.
    """

    INVENTORY_PAGE = "products"

    # ── actions ──────────────────────────────────────────────
    def open_products(self, base_url: str) -> None:
        """Navigate directly to the All Products listing."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.confirm_arrival()

    def search_for(self, term: str) -> None:
        """Type a term into the search box and submit.

        Confirms it is on this page first: filling a field that is not on
        screen would wait the full timeout and then blame the field rather
        than the missing navigation.
        """
        self.require_own_page()
        self.fill(self.sel("search_input"), term)
        self.click(self.sel("search_button"))

    def view_product(self, name: str) -> None:
        """Open the product detail page for the card matching `name`.

        Scopes to the card containing the product name and clicks its View
        Product link, rather than indexing into a family that is doubled per
        card. Landing on the detail page is confirmed by that page's own
        object in the step definitions.
        """
        self.click_in_row(
            self.sel("product_cards"),
            name,
            self.sel("view_product_links"),
        )

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self) -> bool:
        """True once the All Products listing is on screen. WAITS for it.

        Probes the declared readiness element (the All Products heading),
        which is present on the unsearched listing.
        """
        return self.is_showing(self.sel("all_products_heading"))

    def is_search_executed(self) -> bool:
        """True once a search has actually run. WAITS for the heading.

        The 'Searched Products' heading is the only reliable signal that the
        search EXECUTED — a result count alone cannot tell 'search returned
        one product' from 'search never ran and the full catalogue is shown'.
        Call this only where a search is expected to have run; it times out
        otherwise.
        """
        return self.is_showing(self.sel("searched_products_heading"))

    def get_result_names(self) -> List[str]:
        """Every product name shown in the results, as a list of strings.

        The name family is doubled per card, so duplicates are expected; use
        containment when asserting a product IS present.
        """
        return self.get_all_texts(self.sel("product_names"))

    def get_result_card_count(self) -> int:
        """Number of product result cards currently displayed.

        product_cards is one element per card (not doubled), so this is a
        true card count. Used to assert an empty search result — this app
        renders NO cards rather than an explicit 'no results' message.
        """
        return self.get_count(self.sel("product_cards"))
