"""
ProductsPage — the All Products / search listing at /products.

Selectors come from the app inventory (`pages.products`); this file never
contains a literal selector string. Look each element up by its `elements`
KEY with self.sel("<key>").

App: https://automationexercise.com

Naming: the class already says "Products", so search_for() carries the noun
implicitly and does not repeat it. Methods that name their subject
(open_listing, open_product) never collide once reduced to meaning-bearing
words — see the naming rule. Methods that land the browser on ANOTHER page
(open_product) do not confirm arrival here — the destination page object does.

Several families on this page are MULTI-MATCH (product_cards, product_names,
add_to_cart_buttons, view_product_links) and some are DOUBLED per card. They
are only ever read with plural helpers, or scoped to one card via
click_in_row(); they are never clicked or asserted on as a whole.
"""
from typing import Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class ProductsPage(BasePage):
    """All Products / search listing. Selectors: see `pages.products`."""

    INVENTORY_PAGE = "products"

    # ── actions ──────────────────────────────────────────────
    def open_listing(self, base_url: str) -> None:
        """Navigate directly to the all-products listing and confirm arrival.

        The path comes from the inventory, so it is never duplicated here.
        """
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.confirm_arrival()

    def search_for(self, term: str) -> None:
        """Type a term into the search box and submit.

        Confirms we are on this page first — filling a field that is not on
        screen would wait the full Playwright timeout and then blame the
        locator, which reads like a broken selector when the page is simply
        wrong.

        After submitting, waits for the 'Searched Products' heading. That
        heading is the only reliable signal the search EXECUTED — a result
        count alone cannot distinguish 'search returned one product' from
        'search never ran and the full catalogue is still shown'.
        """
        self.require_own_page()
        self.fill(self.sel("search_input"), term)
        self.click(self.sel("search_button"))
        self.wait_visible(self.sel("searched_products_heading"))

    def open_product(self, name: str) -> None:
        """Open the detail page for the product card whose name is `name`.

        Scopes to the card CONTAINING the product name and clicks its
        View Product link, rather than indexing into a doubled family.
        Landing on the product detail page is confirmed by that page's own
        page object, so this method does not call confirm_arrival().
        """
        self.click_in_row(
            self.sel("product_cards"),
            name,
            self.sel("view_product_links"),
        )

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the all-products listing is on screen. WAITS for it.

        Probes the 'All Products' heading, which is present on the unsearched
        listing — the page's readiness element for the loaded-but-unsearched
        state.
        """
        return self.is_showing(
            self.sel("all_products_heading"), timeout_ms=timeout_ms
        )

    def get_result_product_names(self) -> list[str]:
        """Every product name currently displayed, as a list of strings.

        The product_names family is MULTI-MATCH and doubled per card, so the
        same name appears more than once — callers should assert containment,
        not an exact list. Read with the plural helper; never index into it.
        """
        return self.get_all_texts(self.sel("product_names"))

    def has_result_product(self, name: str) -> bool:
        """True once a result card for `name` is present. WAITS for it.

        Call this only where the product is EXPECTED among the results. It
        waits for at least one matching card, so it can answer 'no' only by
        exhausting its timeout — do not use it to assert absence.
        """
        self.wait_for_any(self.sel("product_cards"))
        return any(name in n for n in self.get_result_product_names())

    def get_result_count(self) -> int:
        """Number of product result cards currently shown (no waiting).

        Reads the product_cards family, which is one element per card (NOT
        doubled). Use this to assert an empty result set: an empty search on
        this site renders no cards and no empty-state text, so counting cards
        is the only way to verify 'no results'.
        """
        return self.get_count(self.sel("product_cards"))
