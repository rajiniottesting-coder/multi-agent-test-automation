"""
ProductsPage — the All Products listing (/products).

Navigation surface for cart scenarios: the shopper opens a named product's
details page by clicking the 'View Product' link on that product's card. This
page object does NOT add to cart from the listing — the listing's add-to-cart
family matches 68 elements (doubled per card) and is a strict-mode trap; adding
belongs on the product detail page, which exposes a single unique control.

Category browsing (product-categories feature) is additive: the sidebar's
category and subcategory controls are NOT in the inventory, so category
navigation is driven by opening the category URL directly and by expanding /
clicking the sidebar via ARIA accessible names. See the category methods below
and the notes.

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

    def open_category(self, base_url: str, category_id: str) -> None:
        """Open a category products page directly by its numeric id.

        Used for the negative scenario, where a nonexistent id must load
        without being resolved from a sidebar link. The category URL template
        (/category_products/{id}) is NOT in the inventory as its own page, so
        the path is built here from the known pattern rather than page_url().
        confirm_arrival() is NOT called: this page object declares /products,
        and a category page is a different path — asserting arrival here would
        be wrong. navigate() already fails fast if the server did not serve it.
        """
        self.navigate(f"{base_url.rstrip('/')}/category_products/{category_id}")

    def open_category_from_sidebar(self, category: str, subcategory: str) -> None:
        """Expand a sidebar category and click one of its subcategories.

        Confirms it is ON the listing first: clicking the sidebar as an opening
        move from somewhere else would not fail fast — Playwright waits the full
        timeout and then blames the link. The category heading (e.g. 'Women')
        and the subcategory (e.g. 'Dress') are addressed by their ARIA link
        accessible names via click_role, because the sidebar's category /
        subcategory controls are NOT in the inventory's element map.
        """
        self.require_own_page()
        self.click_role("link", category)
        self.click_role("link", subcategory)

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

    def is_on_category_page(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the URL is a category_products page. WAITS for the change.

        A category page lives at /category_products/<id>, a different path from
        this page object's declared /products. Clicking Women > Dress navigates
        there, so this confirms the browser moved off the all-products listing
        and onto a category page. WAITS, so call it only where arrival on a
        category page is expected.
        """
        try:
            self.wait_for_url("**/category_products/**", timeout_ms=timeout_ms)
            return True
        except Exception:
            logger.info("Not on a category_products page; current url=%s", self.get_url())
            return False

    def category_heading(self) -> str:
        """The category page's heading text, e.g. 'Women - Dress Products'.

        WAITS for it. On a category page this app renders the category name in
        the SAME heading element it uses for 'Searched Products', so this reads
        the searched_products_heading key. Compare case-insensitively; CSS may
        upper-case it.
        """
        self.wait_visible(self.sel("searched_products_heading"))
        return self.get_text(self.sel("searched_products_heading"))

    def category_heading_matches(self, expected: str) -> bool:
        """True if the category heading CONTAINS `expected`, case-insensitively.

        WAITS for the heading. Containment and case-insensitive because CSS
        often transforms the displayed case and the heading may carry extra
        words around the category name.
        """
        shown = self.category_heading()
        return expected.casefold() in shown.casefold()

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
