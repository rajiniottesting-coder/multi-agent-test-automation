"""
ProductsPage — the /products listing and search screen.

Selectors come from the `products` entry in the app inventory. This page carries
one search form and a family of product cards; searching submits to the same
page and swaps the 'All Products' heading for 'Searched Products'.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class ProductsPage(BasePage):
    """Product listing and search. Selectors: see `products` in the inventory.

    Every result-related key here is a FAMILY (product_cards, product_names,
    view_product_links). Read them with the plural helpers; to open ONE product
    scope to the card that contains its name.
    """

    INVENTORY_PAGE = "products"

    # ── actions ──────────────────────────────────────────────
    def open_listing(self, base_url: str) -> None:
        """Navigate to the products listing page."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.confirm_arrival()

    def search_for(self, term: str) -> None:
        """Enter a search term and submit.

        An empty term is legal: the field is cleared and the search submitted,
        which is exactly the empty-search validation case.
        """
        self.fill(self.sel("search_input"), term)
        self.click(self.sel("search_button"))

    def open_product(self, product_name: str) -> None:
        """Open the detail page for one product from the result cards.

        Scopes to the card containing the product name rather than indexing a
        doubled family, then clicks that card's View Product link.
        """
        self.click_in_row(
            self.sel("product_cards"),
            product_name,
            self.sel("view_product_links"),
        )

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the products listing is on screen. WAITS for it.

        Probes the All Products heading, which is present on the unsearched
        listing this page object always opens.
        """
        return self.is_showing(self.sel("all_products_heading"), timeout_ms=timeout_ms)

    def has_search_executed(self, timeout_ms: Optional[int] = None) -> bool:
        """True once a search has run. WAITS for the Searched Products heading.

        Call this only where a search IS expected to have executed — it is the
        only reliable signal distinguishing 'search returned one product' from
        'search never ran and the full catalogue is still shown'.
        """
        return self.is_showing(self.sel("searched_products_heading"), timeout_ms=timeout_ms)

    def has_product_card(self, product_name: str) -> bool:
        """True if a result card for the named product is present. WAITS for it.

        Call this only when the product is EXPECTED. To assert a search
        returned nothing, use get_result_count() and expect 0.
        """
        self.wait_for_row(self.sel("product_cards"), product_name, present=True)
        return True

    def get_result_count(self) -> int:
        """Number of result cards currently shown.

        A snapshot, used to assert an EMPTY search result (expect 0). The
        empty-search case renders no cards and no empty-state message, so
        counting is the only signal available.
        """
        return self.get_count(self.sel("product_cards"))

    def get_product_names(self) -> list[str]:
        """Visible names of all result cards, in DOM order."""
        return self.get_all_texts(self.sel("product_names"))
