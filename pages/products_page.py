"""
ProductsPage — the /products listing.

Search the catalogue, inspect results, and open a product's detail page.

Selectors come from `pages.products` in the app inventory; this file never
holds a literal selector. See pages/login_page.py for the reference style.

App: https://automationexercise.com
"""
from typing import List

from pages.base_page import BasePage
from pages.product_detail_page import ProductDetailPage


class ProductsPage(BasePage):
    """The /products listing: search box, result cards, per-product links.

    Selectors: see `pages.products` in the app inventory. Several keys are a
    FAMILY (product_cards, product_names, view_product_links, add_to_cart_buttons)
    and several of those are DOUBLED per card — read them with the plural
    helpers, and scope to a card by its text rather than indexing.
    """

    INVENTORY_PAGE = "products"

    # ── navigation ───────────────────────────────────────────
    def open_listing(self, base_url: str) -> None:
        """Navigate directly to the /products listing."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.confirm_arrival()

    def is_loaded(self) -> bool:
        """True once the listing is on screen. WAITS for it.

        Probes the All Products heading, which is the readiness signal for the
        unsearched listing.
        """
        return self.is_showing(self.sel("all_products_heading"))

    # ── search ───────────────────────────────────────────────
    def search_for(self, term: str) -> None:
        """Type a search term and submit it. Stays on /products.

        Search matches on product NAME and reloads the same page.
        """
        self.fill(self.sel("search_input"), term)
        self.click(self.sel("search_button"))

    def search_has_run(self) -> bool:
        """True once the search has EXECUTED. WAITS for it.

        Probes the Searched Products heading, which replaces the All Products
        heading only after a search runs. This is the only reliable signal that
        the search actually happened — a result count alone cannot tell an
        empty result from a search that never ran.

        Call this only where a search is expected to have completed.
        """
        return self.is_showing(self.sel("searched_products_heading"))

    # ── results ──────────────────────────────────────────────
    def result_card_count(self) -> int:
        """Number of result cards currently displayed.

        Uses the product_cards family, which is NOT doubled (one per card),
        so this is the honest count of results. A search matching nothing
        renders zero cards — this app shows no empty-state message.
        """
        return self.get_count(self.sel("product_cards"))

    def has_product(self, product_name: str) -> bool:
        """True once a result card containing `product_name` is present. WAITS.

        Waits for the card row rather than snapshotting the name family: right
        after a search the listing is still settling, and a snapshot would race
        it. Scopes by row text, which is robust to the product-name family
        being doubled per card.

        Call this only where the product is EXPECTED — it can answer "no" only
        by timing out. To assert a product is ABSENT, count the cards instead
        (result_card_count() == 0), since this app renders no empty-state text.
        """
        try:
            self.wait_for_row(
                self.sel("product_cards"), product_name, present=True
            )
            return True
        except Exception:
            return False

    # ── open a product ───────────────────────────────────────
    def open_product(self, product_name: str) -> ProductDetailPage:
        """Click the View Product link on `product_name`'s card and land on its
        detail page.

        Scopes to the card containing the product name rather than indexing
        into a family, because the product-name and add-to-cart families are
        doubled per card and their indices do not line up with the card family.

        Returns the ProductDetailPage, whose confirm_arrival() proves the click
        landed on a product-detail URL rather than being swallowed by an ad
        interstitial.
        """
        self.click_in_row(
            self.sel("product_cards"),
            product_name,
            self.sel("view_product_links"),
        )
        detail = ProductDetailPage(self.page)
        detail.confirm_arrival()
        return detail
