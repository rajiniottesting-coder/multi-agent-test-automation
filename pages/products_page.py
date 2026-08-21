"""
ProductsPage — the /products listing and search screen.

Selectors come from the app inventory (`pages.products`), never from a literal
in this file: set INVENTORY_PAGE, then use self.sel("<element_key>").

Search on this app submits to the same /products URL and swaps the
'All Products' heading for 'Searched Products' — that heading is the only
reliable signal that the search actually EXECUTED, so readers wait on it before
reading results. Result families (cards, names, View Product links) are
multi-match; act on ONE member by scoping to the card containing the product
name with click_in_row(), and read the families with get_all_texts / get_count.

App: https://automationexercise.com
"""
from typing import List

from pages.base_page import BasePage


class ProductsPage(BasePage):
    """Products listing / search. Selectors: see `pages.products` in the inventory."""

    INVENTORY_PAGE = "products"

    # ── actions ──────────────────────────────────────────────
    def open_listing(self, base_url: str) -> None:
        """Navigate directly to the /products listing."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    def search_for(self, term: str) -> None:
        """Type a search term and submit it.

        Search matches on product NAME and reloads the same /products URL. After
        this the 'Searched Products' heading replaces 'All Products'; wait on
        was_search_executed() before reading results.
        """
        self.fill(self.sel("search_input"), term)
        self.click(self.sel("search_button"))

    def open_product(self, product_name: str) -> None:
        """Open a product's detail page via the View Product link on its card.

        Scopes to the card containing `product_name` rather than indexing across
        the doubled name family, then clicks that card's View Product link.
        """
        self.click_in_row(
            self.sel("product_cards"),
            product_name,
            self.sel("view_product_links"),
        )

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self) -> bool:
        """True once the listing is on screen. WAITS for it.

        Probes the 'All Products' heading, which is present on the freshly
        loaded, unsearched listing.
        """
        return self.is_showing(self.sel("all_products_heading"))

    def was_search_executed(self) -> bool:
        """True once the 'Searched Products' heading is shown. WAITS for it.

        This heading replaces 'All Products' only after a search runs, so it is
        the reliable signal that the search EXECUTED — a result count alone
        cannot tell an empty match from a search that never ran.
        """
        return self.is_showing(self.sel("searched_products_heading"))

    def get_result_names(self) -> List[str]:
        """Visible product names across all result cards, in DOM order.

        The name family renders twice per card, so this list contains each name
        twice; assert presence with containment rather than by exact length.
        """
        return self.get_all_texts(self.sel("product_names"))

    def has_product(self, product_name: str) -> bool:
        """True if a result card containing `product_name` is present. WAITS for it."""
        self.wait_for_row(self.sel("product_cards"), product_name, present=True)
        return True

    def get_result_card_count(self) -> int:
        """Number of result cards currently displayed (no waiting).

        Uses the non-doubled product_cards family — one per product. Suitable
        for reading a count; for asserting a specific count after a change use
        assert_result_card_count().
        """
        return self.get_count(self.sel("product_cards"))

    def assert_no_results(self) -> None:
        """Wait until zero result cards are displayed.

        An empty search on this app renders NO cards rather than an empty-state
        message, so absence is asserted by counting cards down to zero.
        """
        self.wait_for_count(self.sel("product_cards"), 0)

    def get_product_price(self, product_name: str) -> str:
        """Price text shown on the card for `product_name` (e.g. 'Rs. 500').

        Reads the whole card row's text and returns it; assert on the price as a
        substring since a card row concatenates name, price and controls.
        """
        row = self.row_containing(self.sel("product_cards"), product_name)
        return row.inner_text().strip()
