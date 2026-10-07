"""
ProductsPage — the Products listing and search screen.

Selectors come from the `products` page in the app inventory. Set
INVENTORY_PAGE and resolve every element through self.sel("<key>").

Key behaviours this page must support for the shopping-session feature:
  - open the listing (navigate, confirm arrival)
  - search for a product by name
  - assert a result card IS present (waiting, by product name)
  - assert NO result cards are displayed (empty search renders no cards)
  - open a product by name via its View Product link

Notes on the inventory's traps that shape the methods below:
  - product_names / add_to_cart_buttons are DOUBLED per card (card + hover
    overlay), so never index into them; read with get_all_texts and open a
    product by scoping to its card with click_in_row.
  - An empty-match search renders NO result cards rather than an empty-state
    message, so absence is asserted by counting cards, not by looking for text.

App: https://automationexercise.com
"""
from typing import Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class ProductsPage(BasePage):
    """Products listing and search. Selectors: see `products` in the inventory.

    The all-products heading is the most state-independent readiness signal on
    this page: the search REPLACES it with 'Searched Products', so it cannot be
    the readiness probe for every state. The listing's distinctive, always-
    present control is the search box, which survives both the unsearched and
    searched states — so is_loaded() probes that.
    """

    INVENTORY_PAGE = "products"

    # ── actions ──────────────────────────────────────────────
    def open_listing(self, base_url: str) -> None:
        """Navigate to the Products listing and confirm arrival.

        Args:
            base_url: application base URL supplied by the `base_url` fixture.
                      The path comes from the inventory.
        """
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.confirm_arrival()

    def search_for(self, term: str) -> None:
        """Enter a search term and submit it.

        First action of the method, so it confirms it is on this page before
        filling — otherwise a stray scenario pays the full Playwright timeout
        and the failure blames the search field rather than the wrong page.
        """
        self.require_own_page()
        self.fill(self.sel("search_input"), term)
        self.click(self.sel("search_button"))

    def open_product(self, name: str) -> None:
        """Open the product detail page for the card whose name is `name`.

        The View Product link family has one entry per card, but product_names
        is DOUBLED per card, so an index taken from the names cannot be applied
        to the links. Scope to the card containing the name and click the View
        Product link inside it instead.
        """
        self.click_in_row(
            self.sel("product_cards"),
            name,
            self.sel("view_product_links"),
        )

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the Products page is on screen. WAITS for it.

        Probes the search box: it is present on both the unsearched listing and
        the searched-results view, so it holds in every state this page can be
        in. The all-products heading would not — a search replaces it.
        """
        return self.is_showing(self.sel("search_input"), timeout_ms=timeout_ms)

    def has_product_card(self, name: str) -> bool:
        """True once a result card for `name` is displayed. WAITS for it.

        Call this only where the card is expected to be present. To assert that
        NO cards are displayed, use get_result_card_count(), which does not
        wait for cards that will never appear.
        """
        self.wait_for_row(self.sel("product_cards"), name, present=True)
        return True

    def get_result_card_count(self) -> int:
        """Return how many product result cards are currently displayed.

        Does NOT wait: an empty-match search renders zero cards and no empty-
        state message, so a count of 0 is the expected, legitimate answer here.
        Use this to assert absence of results — never a waiting reader, which
        would time out instead of returning zero.
        """
        return self.get_count(self.sel("product_cards"))
