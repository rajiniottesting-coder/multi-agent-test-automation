"""
ProductsPage — the /products all-products listing.

Selectors come from `pages.products` in the app inventory; this file holds no
literal selector strings. Search, count result cards, and open a product by
its View Product link.

App: https://automationexercise.com
"""
from pages.base_page import BasePage


class ProductsPage(BasePage):
    """All Products listing. Selectors: see `pages.products` in the inventory.

    Several keys here match a FAMILY of elements (product_cards, product_names,
    view_product_links). They are read with the plural helpers or scoped to one
    card by text; they are never clicked or asserted on as a whole.
    """

    INVENTORY_PAGE = "products"

    # ── actions ──────────────────────────────────────────────
    def open_listing(self, base_url: str) -> None:
        """Navigate to the all-products listing."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.confirm_arrival()

    def search_for(self, term: str) -> None:
        """Type a search term and submit it.

        The search posts back to the same page; assert on has_searched()
        afterwards to confirm it actually ran before reading results.
        """
        self.fill(self.sel("search_input"), term)
        self.click(self.sel("search_button"))

    def open_product(self, product_name: str) -> None:
        """Open a product's detail page via its View Product link.

        Scopes to the card that contains `product_name` and clicks the
        View Product link inside it, so the correct product opens even though
        the link is a multi-match family across every card.
        """
        self.click_in_row(
            self.sel("product_cards"),
            product_name,
            self.sel("view_product_links"),
        )

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self) -> bool:
        """True once the all-products listing is on screen. WAITS for it.

        Probes the All Products heading, which is the listing's readiness
        signal in its unsearched state.
        """
        return self.is_showing(self.sel("all_products_heading"))

    def has_searched(self) -> bool:
        """True once a search has executed. WAITS, and times out if it has not.

        Probes the 'Searched Products' heading, which is the only reliable
        signal that the search actually ran — a result count alone cannot tell
        'the search returned one product' from 'the search never ran'. Call
        this only where a search is expected to have run.
        """
        return self.is_showing(self.sel("searched_products_heading"))

    def get_result_count(self) -> int:
        """Number of product cards currently rendered (no waiting).

        Used to assert an empty result set: a non-matching search renders NO
        cards and NO empty-state message, so absence is confirmed by a count
        of zero rather than by any text element.
        """
        return self.get_count(self.sel("product_cards"))

    def get_product_names(self) -> list[str]:
        """Visible product names across all result cards, in DOM order."""
        return self.get_all_texts(self.sel("product_names"))

    def has_product(self, product_name: str) -> bool:
        """True once a card for `product_name` is present. WAITS for it.

        Call this only where the product is expected to be present; to assert
        an empty result set use get_result_count() instead, which does not
        wait.
        """
        self.wait_for_row(self.sel("product_cards"), product_name, present=True)
        return True
