"""
ProductsPage — the /products listing and its search.

Selectors come from the `products` page in the app inventory. This page object
is written for the shopping-session feature: open the listing, run a search,
assert which products the search returned, count result cards, and open one
product via its View Product link.

Two families on this page are DOUBLED per card (product_names and
add_to_cart_buttons render twice each), so this file never indexes into them
and never acts on the add-to-cart control here — a cart scenario adds a product
from the product detail page, where the control is unique. To open one product
we scope to the card containing the name and click its View Product link.

App: https://automationexercise.com
"""
from typing import List

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class ProductsPage(BasePage):
    """The All Products listing. Selectors: see `products` in the app inventory."""

    INVENTORY_PAGE = "products"

    # ── actions ──────────────────────────────────────────────
    def open_listing(self, base_url: str) -> None:
        """Navigate to the /products listing.

        Args:
            base_url: application base URL from the `base_url` fixture. The path
                      is read from the inventory, so it is not duplicated here.
        """
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.confirm_arrival()

    def search_for(self, term: str) -> None:
        """Type a search term and submit.

        Confirms it is on this page first: a fill from the wrong page waits the
        full Playwright timeout and then blames the field's locator, which reads
        like a broken selector when the page is simply wrong.

        After submitting, waits for the Searched Products heading, which is the
        only reliable signal the search actually executed — a result count
        alone cannot tell an empty match from a search that never ran.
        """
        self.require_own_page()
        self.fill(self.sel("search_input"), term)
        self.click(self.sel("search_button"))
        self.wait_visible(self.sel("searched_products_heading"))

    def submit_search_empty(self) -> None:
        """Clear the search box and submit with no term.

        The documented edge case: an empty search matches the whole catalogue.
        Waits for the Searched Products heading to confirm the search ran.
        """
        self.require_own_page()
        self.clear(self.sel("search_input"))
        self.click(self.sel("search_button"))
        self.wait_visible(self.sel("searched_products_heading"))

    def view_product(self, product_name: str) -> None:
        """Open the detail page for `product_name` via its View Product link.

        Scopes to the CARD that contains the product name and clicks the View
        Product link inside it — never indexes across the doubled name family.
        Leaving this page, so it does not confirm arrival here; the product
        detail page object confirms its own arrival.
        """
        self.click_in_row(
            self.sel("product_cards"),
            product_name,
            self.sel("view_product_links"),
        )

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self) -> bool:
        """True once the All Products heading is on screen. WAITS for it.

        The unsearched listing's state-independent readiness element: it is
        present when the page opens, before any search replaces it.
        """
        return self.is_showing(self.sel("all_products_heading"))

    def get_result_names(self) -> List[str]:
        """Every displayed product name, as a list of strings.

        Reads the name family with get_all_texts(); the family is doubled per
        card, so names repeat, which is fine for a containment check but must
        not be used as a card count. Use get_result_card_count() to count.
        """
        return self.get_all_texts(self.sel("product_names"))

    def get_result_card_count(self) -> int:
        """Number of product result cards currently displayed.

        Counts the card family (one per card, NOT doubled), so this is the
        honest card count. A snapshot read: a search is a full reload, and the
        search_for/submit_search_empty methods already waited for the searched
        heading before this is called, so the results have settled.
        """
        return self.get_count(self.sel("product_cards"))

    def has_result_named(self, product_name: str) -> bool:
        """True if a card whose name contains `product_name` is displayed.

        Presence check: waits for the card containing the name to appear before
        answering, so it does not race the search reload. Call this only where
        presence is the expected answer.
        """
        self.wait_for_row(self.sel("product_cards"), product_name, present=True)
        return True
