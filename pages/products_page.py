"""
ProductsPage — the All Products listing and search screen.

Selectors come from the `products` page in the app inventory. This page carries
several FAMILY selectors (product_cards, product_names, add_to_cart_buttons,
view_product_links) that match many elements, and two of them are DOUBLED per
card. Never click, fill or assert on a family as a whole — read it with the
plural helpers, or scope to a single card by the product name.

Reaching this page by clicking the nav Products link is the NavPage's job, not
this page object's: that link belongs to the `nav` inventory page and this
object may only resolve keys from `products`. The step definition that owns the
flow drives the nav link, then confirms arrival with this object's is_loaded().

App: https://automationexercise.com
"""
from typing import Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class ProductsPage(BasePage):
    """All Products listing + search. Selectors: see `products` in the inventory.

    The listing shows one card per product. Search matches on product NAME and
    submits to this same page, replacing the 'All Products' heading with a
    'Searched Products' heading — the only reliable signal that a search
    actually ran.
    """

    INVENTORY_PAGE = "products"

    # ── actions ──────────────────────────────────────────────
    def open_listing(self, base_url: str) -> None:
        """Navigate directly to the All Products listing.

        Args:
            base_url: application base URL from the `base_url` fixture. The
                      path comes from the inventory, so it is not duplicated.
        """
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.confirm_arrival()

    def search_for(self, term: str) -> None:
        """Type a search term and submit.

        Confirms it is on this page first: filling a field that is not on
        screen does not fail fast — Playwright waits the full timeout and then
        blames the locator, which reads like a broken selector when the page
        is simply wrong.
        """
        self.require_own_page()
        self.fill(self.sel("search_input"), term)
        self.click(self.sel("search_button"))

    def open_product(self, name: str) -> None:
        """Open the detail page for the product whose card contains `name`.

        Scopes to the ONE card containing the product name and clicks its
        View Product link, rather than indexing across the doubled families.
        """
        self.click_in_row(
            self.sel("product_cards"),
            name,
            self.sel("view_product_links"),
        )

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the listing is on screen. WAITS for it.

        Probes the products readiness element — the search box, which is
        present whether or not a search has run, unlike the heading, which a
        search replaces.
        """
        return self.is_showing(self.sel("search_input"), timeout_ms=timeout_ms)

    def wait_for_search_executed(self) -> None:
        """Wait until the 'Searched Products' heading confirms a search ran.

        A result count alone cannot distinguish 'the search returned one
        product' from 'the search never ran and the full catalogue is still
        showing'. This heading is the reliable signal.
        """
        self.wait_visible(self.sel("searched_products_heading"))

    def get_result_names(self) -> list[str]:
        """Every product name shown, as a list of strings.

        product_names is doubled per card, so a name may appear twice; use
        containment when asserting a product IS present rather than counting.
        """
        return self.get_all_texts(self.sel("product_names"))

    def has_result(self, name: str) -> bool:
        """True once a card for `name` is present in the results. WAITS for it.

        Call this only where the product is EXPECTED to be present — it waits
        for the card and returns True once found, and would time out rather
        than return False for an absent product.
        """
        self.wait_for_row(self.sel("product_cards"), name, present=True)
        return True

    def has_result_cards(self) -> bool:
        """True once at least one product card is shown. WAITS for one.

        Call this where cards are EXPECTED (an empty query returns the full
        catalogue). It waits for at least one card to appear and would time
        out rather than return False if none ever do.
        """
        self.wait_for_any(self.sel("product_cards"), present=True)
        return True

    def has_no_result_cards(self) -> bool:
        """True once NO product cards are shown. WAITS for them to be gone.

        An empty search on this app renders no result cards rather than an
        empty-state message, so absence is asserted by the card family
        emptying. Call this only where an empty result is EXPECTED — it waits
        for the family to reach zero and would time out rather than return
        False if cards remain.
        """
        self.wait_for_any(self.sel("product_cards"), present=False)
        return True
