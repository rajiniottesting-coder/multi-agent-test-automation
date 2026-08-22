"""
ProductsPage — the /products listing and search screen.

Selectors come from the `products` page in the app inventory; this file holds
no literal selector strings. Methods are business verbs that name what they act
on, per the naming rule (search_for, not search_products_for).

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class ProductsPage(BasePage):
    """Product listing and search. Selectors: see `products` in the inventory.

    The listing renders product names and Add-to-cart controls TWICE per card
    (card + hover overlay), so those families have double the members you would
    expect. Read them with get_all_texts / get_count and act on ONE product by
    scoping to the card via its View Product link.
    """

    INVENTORY_PAGE = "products"

    # ── actions ──────────────────────────────────────────────
    def open_listing(self, base_url: str) -> None:
        """Navigate to the /products listing page."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    def confirm_arrival(self, **params: object) -> None:
        """Confirm the browser reached the listing; recover if an ad ate it."""
        super().confirm_arrival(**params)

    def search_for(self, term: str) -> None:
        """Type a search term and submit; the results reload on this page.

        Search matches on product NAME. After this returns, confirm the search
        actually executed with search_executed() before reading results — a
        result count alone cannot distinguish 'one match' from 'search never
        ran and the full catalogue is still showing'.
        """
        self.fill(self.sel("search_input"), term)
        self.click(self.sel("search_button"))

    def open_product(self, product_name: str) -> None:
        """Open the detail page for the product whose card contains the name.

        Clicks the View Product link inside that product's card, scoping to the
        row so the multi-match family is never clicked as a whole.
        """
        self.click_in_row(
            self.sel("product_cards"),
            product_name,
            self.sel("view_product_links"),
        )

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the listing is on screen. WAITS for it.

        Probes the All Products heading, present on the unsearched listing.
        """
        return self.is_showing(self.sel("all_products_heading"), timeout_ms=timeout_ms)

    def search_executed(self, timeout_ms: Optional[int] = None) -> bool:
        """True once a search has run. WAITS, and times out if it has not.

        Call this only where a search is expected to have executed. It probes
        the 'Searched Products' heading, which replaces the All Products
        heading once results are rendered — the only reliable signal that the
        search ran rather than the full catalogue still showing.
        """
        return self.is_showing(self.sel("searched_products_heading"), timeout_ms=timeout_ms)

    def get_result_names(self) -> list[str]:
        """Visible product names in the results, in DOM order.

        The names family is doubled per card, so a product appears twice in
        this list. Use membership (`name in get_result_names()`) rather than
        counting.
        """
        return self.get_all_texts(self.sel("product_names"))

    def has_product(self, product_name: str) -> bool:
        """True if a product with this name is present in the results.

        WAITS for the product's card to appear, so use only where the product
        is expected. For absence, assert on the result-card count instead.
        """
        self.wait_for_row(self.sel("product_cards"), product_name, present=True)
        return True

    def get_result_card_count(self) -> int:
        """Number of result cards showing right now (no waiting).

        A search matching nothing renders NO result cards and no empty-state
        message, so an empty result set is asserted by this count being zero.
        """
        return self.get_count(self.sel("product_cards"))
