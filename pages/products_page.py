"""
ProductsPage — the All Products listing and search screen.

Selectors come from `pages.products` in the app inventory; this file never
holds a literal selector. Methods are business verbs (search_for,
open_product) and every one delegates to a BasePage helper.

The listing page is state-dependent: an unsearched load shows the "All
Products" heading, a search replaces it with "Searched Products". Several
element families (product cards, names, view-product links) match many
elements, so they are read with the plural helpers and never acted on as a
whole. To act on ONE product we scope by the card that contains its name.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class ProductsPage(BasePage):
    """All Products listing. Selectors: see `pages.products` in the inventory."""

    INVENTORY_PAGE = "products"

    # ── actions ──────────────────────────────────────────────
    def search_for(self, term: str) -> None:
        """Type a search term and submit it, staying on /products."""
        self.fill(self.sel("search_input"), term)
        self.click(self.sel("search_button"))

    def open_product(self, product_name: str) -> None:
        """Open the detail page for the card containing `product_name`.

        Scopes to the card carrying the product's name and clicks that card's
        View Product link, so the correct product id is followed even though
        the link family matches every card on the page.
        """
        self.click_in_row(
            self.sel("product_cards"),
            product_name,
            self.sel("view_product_links"),
        )

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the listing is on screen. WAITS for it.

        Probes the search input rather than a heading: the heading text swaps
        between 'All Products' and 'Searched Products' depending on whether a
        search has run, while the search box is present in every state of the
        page.
        """
        return self.is_showing(self.sel("search_input"), timeout_ms=timeout_ms)

    def search_executed(self, timeout_ms: Optional[int] = None) -> bool:
        """True once a search has actually run. WAITS for the signal.

        The 'Searched Products' heading replaces 'All Products' only after the
        search submits, so it is the one reliable proof the search executed —
        a result count alone cannot distinguish 'one match' from 'never ran,
        still showing the full catalogue'.
        """
        return self.is_showing(
            self.sel("searched_products_heading"), timeout_ms=timeout_ms
        )

    def get_result_names(self) -> list[str]:
        """Visible names of every product card in the results.

        The name family is doubled per card (once in the card, once in the
        hover overlay), so the same name appears twice; assert containment
        rather than exact membership count.
        """
        return self.get_all_texts(self.sel("product_names"))

    def has_product(self, product_name: str) -> bool:
        """True if a product whose name contains `product_name` is present."""
        return any(product_name in name for name in self.get_result_names())

    def get_result_card_count(self) -> int:
        """Number of product cards in the results.

        Uses the non-doubled card family, so this is a true card count. Used
        to assert an empty result set — this site renders no empty-state
        message, so absence is asserted by a zero card count.
        """
        return self.get_count(self.sel("product_cards"))
