"""
ProductsPage — the All Products listing and search screen.

Selectors come from the `products` page in the app inventory. This page object
exposes search and result-inspection methods; the add-to-cart flow for a
single product is driven from the product detail page, because the listing's
add-to-cart controls are a doubled family (68 matches) that cannot be clicked
safely.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class ProductsPage(BasePage):
    """All Products listing and search. Selectors: see `products` in the
    app inventory.

    SEARCH SIGNAL. A result count alone cannot tell 'the search returned one
    product' from 'the search never ran and the page still shows the full
    catalogue'. The searched-products heading is the only reliable signal that
    a search EXECUTED, so assert on it before asserting on results.
    """

    INVENTORY_PAGE = "products"

    # ── actions ──────────────────────────────────────────────
    def open_listing(self, base_url: str) -> None:
        """Navigate directly to the All Products listing."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    def search_for(self, term: str) -> None:
        """Type a search term and submit it.

        Search matches on product NAME and submits back to /products. After
        this returns, use wait_until_searched() to confirm the search ran
        before inspecting results.
        """
        self.fill(self.sel("search_input"), term)
        self.click(self.sel("search_button"))

    def open_product(self, product_name: str) -> None:
        """Open the detail page for the named product via its View Product
        link.

        Scopes to the card containing the product name rather than indexing
        into a family, then confirms the detail page was reached — a click can
        be consumed by an ad interstitial without navigating.
        """
        self.click_in_row(
            self.sel("product_cards"),
            product_name,
            self.sel("view_product_links"),
        )

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the search box is on screen. WAITS for it.

        The search input survives every state this page can be in — the full
        listing, a successful search, and an empty result set — so it is a
        state-independent readiness probe, unlike either heading which is
        swapped for the other when a search runs.
        """
        return self.is_showing(self.sel("search_input"), timeout_ms=timeout_ms)

    def wait_until_searched(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the Searched Products heading appears. WAITS for it.

        This is the signal that a search actually EXECUTED. Call it before
        asserting on results — a result count alone cannot distinguish a
        one-product match from the unsearched full catalogue.

        Call this only where a search is expected to have run; it can answer
        'no' only by exhausting its timeout.
        """
        return self.is_showing(
            self.sel("searched_products_heading"), timeout_ms=timeout_ms
        )

    def result_names(self) -> list[str]:
        """Every product name currently shown, as a list of strings.

        The name family is doubled per card (once in the card, once in the
        hover overlay), so a product present once appears twice here. Use
        containment (`name in result_names()`) to assert presence rather than
        counting.
        """
        return self.get_all_texts(self.sel("product_names"))

    def result_card_count(self) -> int:
        """Number of product result CARDS shown. Non-waiting snapshot.

        Reads the card family, which is one-per-card and NOT doubled, so this
        is a true product count. Used to assert an empty result set — this app
        renders no empty-state message for a search matching nothing, so
        counting cards is the only signal.
        """
        return self.get_count(self.sel("product_cards"))
