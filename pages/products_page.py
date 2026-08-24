"""
ProductsPage — the /products catalogue listing and its search.

Selectors come from the `products` page in the app inventory. This page object
never holds a literal selector: it declares INVENTORY_PAGE and resolves each
element via self.sel("<key>").

Search on this app is name-based and submits to the same page. A search that
matches nothing renders NO result cards rather than an empty-state message, so
absence is asserted by counting cards. The 'Searched Products' heading is the
only reliable signal that a search actually EXECUTED (a card count alone cannot
tell 'search returned one product' from 'search never ran, full catalogue still
shown'), so callers that need to know the search happened should wait on it.

App: https://automationexercise.com
"""
from typing import Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class ProductsPage(BasePage):
    """The /products listing. Selectors: see `products` in the app inventory.

    MULTI-MATCH families here (product_cards, product_names, add_to_cart_buttons,
    view_product_links) match many elements — and several are DOUBLED per card
    (each card renders its controls twice, once in the card, once in a hover
    overlay). Never click, fill or assert on those families as a whole. Read
    them with the plural helpers, and act on ONE member by scoping to the card
    that contains the product name via click_in_row().
    """

    INVENTORY_PAGE = "products"

    # ── actions ──────────────────────────────────────────────
    def open_listing(self, base_url: str) -> None:
        """Navigate directly to the /products catalogue listing.

        Args:
            base_url: application base URL from the `base_url` fixture. The path
                      comes from the inventory, so it is never duplicated here.
        """
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.confirm_arrival()

    def search_for(self, term: str) -> None:
        """Enter a search term and submit.

        Fills as its first action, so it confirms it is ON this page first:
        filling a field that is not on screen does not fail fast — Playwright
        waits the full timeout and then blames the locator, which reads like a
        broken selector when the page is simply wrong.
        """
        self.require_own_page()
        self.fill(self.sel("search_input"), term)
        self.click(self.sel("search_button"))

    def open_product(self, product_name: str) -> None:
        """Open the detail page for the product whose card contains `product_name`.

        Scopes to the card that contains the name and clicks the View Product
        link inside it. Does NOT confirm arrival on the detail page — that is
        the destination page object's job, and its URL is a per-product
        template this page cannot assert.
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
        listing that open_listing() lands on.
        """
        return self.is_showing(self.sel("all_products_heading"), timeout_ms=timeout_ms)

    def has_search_executed(self, timeout_ms: Optional[int] = None) -> bool:
        """True once a search has run. WAITS for the 'Searched Products' heading.

        Call this only where a search is EXPECTED to have executed. It is the
        only reliable signal the search ran — a card count cannot distinguish a
        one-result search from the full catalogue still being shown.
        """
        return self.is_showing(self.sel("searched_products_heading"), timeout_ms=timeout_ms)

    def get_result_names(self) -> list[str]:
        """Visible product names currently shown, as a list of strings.

        Reads the multi-match product_names family with the plural helper. The
        family is doubled per card, so names may repeat — use containment when
        asserting a product is present, not an exact count.
        """
        return self.get_all_texts(self.sel("product_names"))

    def has_result(self, product_name: str) -> bool:
        """True once a result card for `product_name` is present. WAITS for it.

        Call this only where the product is EXPECTED in the results. Scopes to
        the card family via wait_for_row, so it waits for the card containing
        the name to render.
        """
        self.wait_for_row(self.sel("product_cards"), product_name, present=True)
        return True

    def get_result_count(self) -> int:
        """Number of product result cards currently rendered (no waiting).

        Reads the product_cards family, which is one element per card (NOT
        doubled). Use this to assert an EMPTY result set: an empty search here
        renders zero cards rather than any empty-state text, so counting is the
        only way to verify absence.
        """
        return self.get_count(self.sel("product_cards"))
