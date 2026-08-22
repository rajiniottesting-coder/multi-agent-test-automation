"""
ProductsPage — the All Products listing and product search.

Selectors come from the `products` page in the app inventory; this file never
holds a literal selector. See pages/login_page.py for the reference style.

Search matching notes worth carrying into the methods:
  - searched_products_heading is the only reliable signal that a search
    EXECUTED. A result count alone cannot tell "returned one product" from
    "the search never ran and the full catalogue is still shown".
  - product_names is a MULTI-MATCH family, doubled per card, so it is read
    with get_all_texts() and never clicked.
  - view_product_links is a MULTI-MATCH family, one per card, scoped by the
    card's product name when a single member must be clicked.
  - product_cards is a MULTI-MATCH family, one per card and NOT doubled, so
    counting it is the way to assert an empty result set.

App: https://automationexercise.com
"""
from typing import List

from pages.base_page import BasePage


class ProductsPage(BasePage):
    """All Products listing and search. Selectors: see `products` in inventory."""

    INVENTORY_PAGE = "products"

    # ── actions ──────────────────────────────────────────────
    def open_listing(self, base_url: str) -> None:
        """Navigate directly to the All Products listing."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.confirm_arrival()

    def search_for(self, term: str) -> None:
        """Type a search term and submit it.

        Search matches on product NAME and reloads the same /products page.
        Call is_search_executed() afterwards before asserting on results.
        """
        self.fill(self.sel("search_input"), term)
        self.click(self.sel("search_button"))

    def open_product(self, product_name: str) -> None:
        """Open the product detail page for the card carrying `product_name`.

        Scopes to the card containing the name and clicks its View Product
        link, so it works despite view_product_links being a MULTI-MATCH
        family. Uses href-prefixed links, which carry the product id.
        """
        self.click_in_row(
            self.sel("product_cards"),
            product_name,
            self.sel("view_product_links"),
        )

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self) -> bool:
        """True once the All Products listing is on screen. WAITS for it.

        Probes the All Products heading, which is present on the unsearched
        listing that this page loads into.
        """
        return self.is_showing(self.sel("all_products_heading"))

    def is_search_executed(self) -> bool:
        """True once a search has run. WAITS, and times out if none has.

        The Searched Products heading replaces the All Products heading only
        after a search submits, so it is the reliable "the search executed"
        signal. Call this only where a search IS expected to have run — the
        wait pays its full timeout when the heading never appears.
        """
        return self.is_showing(self.sel("searched_products_heading"))

    def get_result_names(self) -> List[str]:
        """Every product name currently in the results, in DOM order.

        product_names is doubled per card, so names appear twice; assert with
        containment (`expected in names`) rather than on the length here.
        """
        return self.get_all_texts(self.sel("product_names"))

    def has_result(self, product_name: str) -> bool:
        """True if a card for `product_name` is in the results. WAITS for it.

        Waits for a row containing the product name, then confirms it is among
        the names. Call this where the product IS expected among the results.
        For the empty-search case, use get_result_card_count() and assert zero.
        """
        self.wait_for_row(self.sel("product_cards"), product_name, present=True)
        return any(product_name in name for name in self.get_result_names())

    def get_result_card_count(self) -> int:
        """Number of result cards shown right now (no waiting).

        product_cards is one per card and NOT doubled. A no-match search
        renders zero cards rather than an empty-state message, so counting
        cards is how absence is asserted on this page. Use this only to READ
        the count; the empty case has no rows to wait for.
        """
        return self.get_count(self.sel("product_cards"))
