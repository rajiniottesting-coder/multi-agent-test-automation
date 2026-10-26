"""
ProductsPage — the All Products listing (/products).

Navigation surface for cart scenarios: the shopper opens a named product's
details page by clicking the 'View Product' link on that product's card. This
page object does NOT add to cart from the listing — the listing's add-to-cart
family matches 68 elements (doubled per card) and is a strict-mode trap; adding
belongs on the product detail page, which exposes a single unique control.

Selectors: see `products` in the app inventory. No literals live here.

App: https://automationexercise.com
"""
from typing import Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class ProductsPage(BasePage):
    """All Products listing. Selectors: see `pages.products` in the inventory.

    The product_cards / product_names / add_to_cart_buttons / view_product_links
    keys are MULTI-MATCH (and the names/buttons are doubled per card). Never act
    on them as a family — scope to the card that contains the product name.
    """

    INVENTORY_PAGE = "products"

    # ── actions ──────────────────────────────────────────────
    def open_products(self, base_url: str) -> None:
        """Navigate to the All Products listing.

        Args:
            base_url: application base URL from the `base_url` fixture. The path
                      comes from the inventory, so it is never duplicated here.
        """
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.confirm_arrival()

    def open_product_details(self, product_name: str) -> None:
        """Open the details page for the named product via its View Product link.

        Scopes to the product CARD containing the name and clicks the View
        Product link inside that card, so the multi-match link family never has
        to be addressed as a whole. Confirms it is on the listing first — a
        scenario that reached this without opening the listing would otherwise
        pay a full timeout and blame the link selector.
        """
        self.require_own_page()
        self.click_in_row(
            self.sel("product_cards"),
            product_name,
            self.sel("view_product_links"),
        )

    def search_for(self, term: str) -> None:
        """Enter a search term and submit the search form.

        Confirms it is ON the listing first: filling the search box as an
        opening move from somewhere else does not fail fast — Playwright waits
        the full timeout and then blames the field selector. An EMPTY term is
        valid and intentional: submitting it does NOT run a search, it leaves
        the full catalogue in place (see is_full_listing_shown).
        """
        self.require_own_page()
        self.fill(self.sel("search_input"), term)
        self.click(self.sel("search_button"))

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the All Products heading is on screen. WAITS for it.

        The All Products heading is the state-independent readiness signal on
        the unsearched listing — it is present whenever this page is simply
        navigated to, before any search replaces it.
        """
        return self.is_showing(self.sel("all_products_heading"), timeout_ms=timeout_ms)

    def is_search_results_shown(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the Searched Products heading is on screen. WAITS for it.

        This heading is the only reliable signal that a search EXECUTED: a
        result count alone cannot tell 'returned one product' from 'never ran
        and still shows the full catalogue'. Call this only where a run search
        is expected — it times out instead of returning False for an empty
        query, which leaves the All Products heading in place.
        """
        return self.is_showing(self.sel("searched_products_heading"), timeout_ms=timeout_ms)

    def is_full_listing_shown(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the unsearched All Products heading is on screen. WAITS.

        An empty search does NOT run a search: the form submit leaves this
        heading in place and the full catalogue displayed. Use this (never the
        Searched Products reader) for an empty-query scenario.
        """
        return self.is_showing(self.sel("all_products_heading"), timeout_ms=timeout_ms)

    def product_names(self) -> list[str]:
        """Every product name shown on the listing, in DOM order.

        Reads the multi-match name family with the plural helper. The names are
        doubled per card (card + hover overlay), so expect duplicates — use this
        for containment checks ('is this product listed?'), not for counting.
        """
        return self.get_all_texts(self.sel("product_names"))

    def has_product(self, product_name: str) -> bool:
        """True if a product whose name CONTAINS `product_name` is listed.

        Containment, not equality: the name family is read as text, and a card
        name may carry extra words. Use this to assert a known product is
        present in the results.
        """
        return any(product_name in name for name in self.product_names())

    def all_products_match(self, term: str) -> bool:
        """True if EVERY listed product name contains `term`.

        For asserting a search returned only matching products. Returns False
        if any card name does not contain the term. On an empty result set
        there are no names, so this returns True — pair it with has_product to
        prove the result set is non-empty first.
        """
        return all(term in name for name in self.product_names())

    def has_product_cards(self) -> bool:
        """True once AT LEAST ONE product card is rendered. WAITS for one.

        For the positive case where cards are expected. Do NOT negate this to
        assert emptiness — it would time out waiting for a card that never
        appears. Use has_no_product_cards for the empty case.
        """
        self.wait_for_any(self.sel("product_cards"))
        return True

    def has_no_product_cards(self) -> bool:
        """True once NO product cards are rendered. WAITS for them to clear.

        A search matching nothing renders no result cards and no empty-state
        message, so absence of cards IS the signal. This WAITS for the family
        to empty with wait_for_any(present=False), which retries until the
        timeout and logs the reason it gives up — rather than snapshotting the
        count and racing the search response. Call this only where zero cards
        is the expected answer; for a term that matches products it would time
        out instead of returning False.
        """
        self.wait_for_any(self.sel("product_cards"), present=False)
        return True

    def search_results_include(self, product_name: str, timeout_ms: Optional[int] = None) -> bool:
        """True once a product whose name CONTAINS `product_name` is in the results.

        WAITS for the search response: a search submits and reloads the listing,
        so a snapshot taken immediately races the response and reports absence
        while the app is working correctly. This waits for at least one result
        card to render, then checks containment against the name family. Call
        this only where the product is EXPECTED in the results — for a term that
        matches nothing it would time out waiting for a card.
        """
        self.wait_for_any(self.sel("product_cards"), timeout_ms=timeout_ms)
        return self.has_product(product_name)
