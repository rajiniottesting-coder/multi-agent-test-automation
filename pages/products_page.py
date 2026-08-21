"""
ProductsPage — the /products listing and product search screen.

Selectors come from `pages.products` in the app inventory; this file never
holds a literal selector. Set INVENTORY_PAGE, then self.sel("<key>").

Notes on the tricky families here (see the inventory's elements_notes):
  - product_names and add_to_cart_buttons render TWICE per card, so they are
    read-only families here. Assert presence with get_all_texts / get_count.
  - To reach ONE product, scope to the card that contains its name and click
    the View Product link inside it (open_product), then act on the detail
    page, which has a UNIQUE add-to-cart control.
  - searched_products_heading is the only reliable signal that a search
    actually RAN — a result count alone cannot distinguish "one match" from
    "search never executed and the full catalogue is still shown".

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class ProductsPage(BasePage):
    """The /products listing and search. See `pages.products` in the inventory."""

    INVENTORY_PAGE = "products"

    # ── actions ──────────────────────────────────────────────
    def open_listing(self, base_url: str) -> None:
        """Navigate directly to the /products listing."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    def search_for(self, term: str) -> None:
        """Type a search term and submit it.

        Search matches on product name and submits back to /products. Follow
        with was_search_performed() before reading results, since a count alone
        cannot prove the search ran.
        """
        self.fill(self.sel("search_input"), term)
        self.click(self.sel("search_button"))

    def open_product(self, name: str) -> None:
        """Open the product whose card contains `name` via its View Product link.

        Scopes to the card containing the name rather than indexing a doubled
        family, then confirms arrival on the product detail page.
        """
        self.click_in_row(
            self.sel("product_cards"),
            name,
            self.sel("view_product_links"),
        )
        self.wait_for_page_load()

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the products listing is on screen. WAITS for it.

        Probes the readiness element chosen for this page: the 'All Products'
        heading is present on the unsearched listing that open_listing lands on.
        """
        return self.is_showing(self.sel("all_products_heading"), timeout_ms=timeout_ms)

    def was_search_performed(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the 'Searched Products' heading is shown. WAITS for it.

        This heading replaces 'All Products' only after a search executes, so
        it is the reliable signal that the search actually ran.
        """
        return self.is_showing(self.sel("searched_products_heading"), timeout_ms=timeout_ms)

    def get_result_names(self) -> list[str]:
        """Every product name currently rendered in the results, as a list.

        The family renders twice per card, so callers should assert
        containment (name in names) rather than an exact count.
        """
        return self.get_all_texts(self.sel("product_names"))

    def has_product(self, name: str) -> bool:
        """True if a product whose name contains `name` is in the results."""
        return any(name in candidate for candidate in self.get_result_names())

    def get_result_card_count(self) -> int:
        """Number of result CARDS shown (product_cards is one per card).

        Used to assert an empty result set: an unmatched search renders no
        cards and no empty-state message, so absence is asserted by count of
        cards, not by looking for text.
        """
        return self.get_count(self.sel("product_cards"))
