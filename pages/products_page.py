"""
ProductsPage — the All Products / Search listing at /products.

New page object for the shopping-session feature. Conventions copied from
pages/login_page.py:

  - SELECTORS COME FROM THE APP INVENTORY, never a literal here. Set
    INVENTORY_PAGE, then use self.sel("<element key>").
  - methods are business verbs that name what they act on (open_listing,
    search_for), not UI mechanics.
  - every method uses a BasePage helper; no raw self.page.* calls.
  - no assertions here — those belong in step definitions.
  - waiting predicates (is_*, has_*) are documented as waiting.

App: https://automationexercise.com
"""
from typing import Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class ProductsPage(BasePage):
    """All Products / Search listing. Selectors: see `products` in the inventory.

    FAMILY SELECTORS EVERYWHERE. product_cards, product_names,
    add_to_cart_buttons and view_product_links each match many elements, and
    two of them (product_names, add_to_cart_buttons) render TWICE per card.
    Read the families with the plural helpers; act on one member by scoping to
    the card that contains the product name.
    """

    INVENTORY_PAGE = "products"

    # ── actions ──────────────────────────────────────────────
    def open_listing(self, base_url: str) -> None:
        """Navigate to the All Products listing.

        Args:
            base_url: application base URL from the `base_url` fixture. The path
                      comes from the inventory, so it is not duplicated here.
        """
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.confirm_arrival()

    def search_for(self, term: str) -> None:
        """Type a product-name query and submit the search.

        Confirms it is on this page first — a fill that races the wrong page
        would wait the full timeout and then blame the field's selector, which
        is fine. The search submits to the same page and replaces the
        'All Products' heading with 'Searched Products'.
        """
        self.require_own_page()
        self.fill(self.sel("search_input"), term)
        self.click(self.sel("search_button"))

    def open_product(self, name: str) -> None:
        """Open the detail page of the product whose card carries `name`.

        Scopes to the card containing the product name and clicks the
        View Product link INSIDE that card, so the family's many matches never
        trip strict mode. Product detail arrival is confirmed by the
        ProductDetailPage in its own step.
        """
        self.click_in_row(
            self.sel("product_cards"),
            name,
            self.sel("view_product_links"),
        )

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the listing is on screen. WAITS for it.

        Probes the All Products heading, which is the readiness signal for the
        unsearched listing. Call only where being on the listing is expected.
        """
        return self.is_showing(self.sel("all_products_heading"), timeout_ms=timeout_ms)

    def has_run_search(self, timeout_ms: Optional[int] = None) -> bool:
        """True once a search has executed. WAITS for the Searched Products heading.

        This is the ONLY reliable signal that the search ran — a result count
        alone cannot tell 'returned one product' from 'never searched and still
        showing the full catalogue'. Call it before asserting on results, and
        only where a search is expected to have run: it times out otherwise.
        """
        return self.is_showing(self.sel("searched_products_heading"), timeout_ms=timeout_ms)

    def get_result_names(self) -> list[str]:
        """Every product name in the current results, as a list of strings.

        product_names is doubled per card, so a name legitimately appears more
        than once — assert containment, not exact multiplicity.
        """
        return self.get_all_texts(self.sel("product_names"))

    def get_result_count(self) -> int:
        """Number of product result cards currently displayed.

        Uses the un-doubled product_cards family (one per card), so this is a
        true card count rather than double it. A made-up search term renders no
        cards, so this returns 0 for a no-match search.
        """
        return self.get_count(self.sel("product_cards"))
