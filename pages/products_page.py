"""
ProductsPage — the Products listing screen (/products).

Selectors come from `pages.products` in the app inventory; this file resolves
every one through self.sel("<key>") and never writes a literal locator.

App: https://automationexercise.com
"""
from typing import List

from pages.base_page import BasePage


class ProductsPage(BasePage):
    """All Products / Searched Products listing.

    Selectors: see `pages.products` in the app inventory.

    Several inventory keys on this page are MULTI-MATCH families
    (product_cards, product_names, add_to_cart_buttons, view_product_links).
    They are read with plural helpers or scoped to a single card; they are
    never clicked, filled or asserted on as a whole.
    """

    INVENTORY_PAGE = "products"

    # ── actions ──────────────────────────────────────────────
    def open_listing(self, base_url: str) -> None:
        """Navigate to the Products listing and confirm arrival.

        Args:
            base_url: application base URL from the `base_url` fixture. The
                      path comes from the inventory, so it is not duplicated.
        """
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.confirm_arrival()

    def search_for(self, term: str) -> None:
        """Type a product-name query and submit the search.

        Search matches on product name and re-renders this same page. After
        this returns, is_search_executed() is the reliable signal that the
        search actually ran — a result count alone cannot distinguish
        'one match' from 'the search never ran and the full catalogue shows'.
        """
        self.fill(self.sel("search_input"), term)
        self.click(self.sel("search_button"))

    def open_product(self, product_name: str) -> None:
        """Open the product whose card contains `product_name`.

        Scopes to the card containing the name and clicks its View Product
        link, then leaves this page — landing on the product detail page is
        confirmed by that page's own object, not here.
        """
        self.click_in_row(
            self.sel("product_cards"),
            product_name,
            self.sel("view_product_links"),
        )

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self) -> bool:
        """True once the Products listing is on screen. WAITS for it.

        Probes the search input, the one control that survives every state of
        this page: the All Products heading is replaced by Searched Products
        after a search, and result cards come and go, but the search box is
        always present. Delegates to is_showing() so a failed check logs the
        selector, the wait and the URL rather than a bare assert.
        """
        return self.is_showing(self.sel("search_input"))

    def is_search_executed(self) -> bool:
        """True once the 'Searched Products' heading is shown. WAITS for it.

        Call this only where a search is EXPECTED to have run. It is the only
        reliable proof the search executed, so a step asserting a search ran
        should use it. To branch on whether a search ran without paying the
        timeout, this is the wrong tool.
        """
        return self.is_showing(self.sel("searched_products_heading"))

    def has_result_for(self, product_name: str) -> bool:
        """True once a result CARD containing `product_name` is on screen.

        WAITS for it via wait_for_row on the product_cards family, so it is
        the right tool for asserting a search FOUND the product. It can only
        answer 'no' by timing out, so do not use it to branch on whether a
        product is present — call it where presence is the expected answer.
        """
        try:
            self.wait_for_row(self.sel("product_cards"), product_name, present=True)
        except Exception:
            return False
        return True

    def get_result_card_count(self) -> int:
        """Number of product result cards currently rendered.

        Reads product_cards, the one-per-card family (NOT doubled). An empty
        search on this app renders NO cards and NO empty-state message, so a
        zero count is how absence is confirmed here — there is no text to
        wait for. A snapshot, so call it after the search has been confirmed
        with is_search_executed().
        """
        return self.get_count(self.sel("product_cards"))
