"""
ProductsPage — the /products all-products listing and search.

Selectors: see `pages.products` in the app inventory. Every selector is
resolved through self.sel("<key>"); no literal selectors live in this file.

App: https://automationexercise.com
"""
from pages.base_page import BasePage


class ProductsPage(BasePage):
    """The /products listing: navigate, search, assert the search executed,
    read result cards and open a product via its View Product link.

    Selectors: see `pages.products` in the app inventory.

    Readiness note: the inventory carries no explicit `readiness` key, so
    is_loaded() probes `all_products_heading`, the heading shown on the
    unsearched listing. It is the most state-independent element for a
    freshly-navigated page; after a search it is replaced by
    `searched_products_heading`, which search_executed() probes instead.

    Result names are NOT readable as a single field on this page. The only
    name-bearing key, `product_names`, is a multi_match FAMILY (doubled per
    card: card + hover overlay), so reading one member returns a whole card's
    concatenated text rather than an isolated name. There is no cell-scoped
    key for a product name here. Callers therefore assert a product IS present
    with has_result() (which scopes to the card row), never by comparing a
    single reader's value for equality.
    """

    INVENTORY_PAGE = "products"

    # ── actions ──────────────────────────────────────────────
    def open_listing(self, base_url: str) -> None:
        """Navigate to the all-products listing at /products."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.confirm_arrival()

    def search_for(self, term: str) -> None:
        """Type a search term into the search box and submit it.

        Search matches on product NAME and submits back to this page. An empty
        term is valid input for the empty-search scenario, so this fills the
        field (clearing whatever was there) even when `term` is "".
        """
        self.fill(self.sel("search_input"), term)
        self.click(self.sel("search_button"))

    def open_product(self, product_name: str) -> None:
        """Open a product's detail page via the View Product link on its card.

        Scopes to the card containing `product_name` and clicks the View
        Product link inside it, so the correct product is opened even though
        the link family matches one per card.
        """
        self.click_in_row(
            self.sel("product_cards"),
            product_name,
            self.sel("view_product_links"),
        )

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self) -> bool:
        """True once the all-products listing is on screen. WAITS for it.

        Call this only where the unsearched listing is the expected state; it
        times out if the heading never appears. After a search the heading is
        replaced — use search_executed() there instead.
        """
        return self.is_showing(self.sel("all_products_heading"))

    def search_executed(self) -> bool:
        """True once a search has run. WAITS for the Searched Products heading.

        This is the only reliable signal that the search EXECUTED: a result
        count alone cannot distinguish 'the search returned one product' from
        'the search never ran and the page still shows the full catalogue'.
        Call this only where a search is expected to have run; it times out
        otherwise.
        """
        return self.is_showing(self.sel("searched_products_heading"))

    def get_result_count(self) -> int:
        """Number of result cards currently rendered.

        A snapshot with no wait — use it to READ a count, not to assert one
        settles. An empty search renders NO cards rather than an empty-state
        message, so absence of results is confirmed by this being 0.
        """
        return self.get_count(self.sel("product_cards"))

    def has_result(self, product_name: str) -> bool:
        """True once a result card containing `product_name` is present. WAITS,
        and times out if no such card ever appears.

        Scopes to the card ROW containing the name rather than reading the
        name family directly: `product_names` is a doubled multi_match family,
        so a single reader returns a whole card's concatenated text, not an
        isolated name. Call this only where the product is EXPECTED in the
        results; to assert absence, use get_result_count() == 0 instead — this
        would time out rather than return False.
        """
        self.wait_for_row(
            self.sel("product_cards"), product_name, present=True
        )
        return True
