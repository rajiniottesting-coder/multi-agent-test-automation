"""
ProductsPage — the /products listing and search screen.

New page object. Selectors: see `pages.products` in the app inventory.

Conventions (copied from LoginPage, the gold-standard reference):

  - SELECTORS COME FROM THE APP INVENTORY, never a literal in this file.
    Declare INVENTORY_PAGE, then use self.sel("<element_key>").
  - methods are business verbs that say WHAT they act on (search_for,
    open_product_named), not bare verbs.
  - every method uses a BasePage helper; no raw self.page.* calls.
  - readiness probes the declared readiness signal; presence readers WAIT,
    absence probes do NOT.

App: https://automationexercise.com
"""
from typing import Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class ProductsPage(BasePage):
    """The /products listing and search screen.

    The listing carries FAMILY selectors (one member per product card, and
    several of them DOUBLED per card because of the hover overlay). Never click
    or assert on those families as a whole — scope to the card that contains
    the product name, or read the family with the plural helpers.
    """

    INVENTORY_PAGE = "products"

    # ── actions ──────────────────────────────────────────────
    def open_products_page(self, base_url: str) -> None:
        """Navigate to the /products listing.

        Args:
            base_url: application base URL from the `base_url` fixture. The path
                      comes from the inventory, so it is never duplicated here.
        """
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    def search_for(self, term: str) -> None:
        """Type a search term into the search box and submit it.

        This is the FIRST action of the method, so it confirms it is on this
        page before filling — a fill against a field that is not on screen does
        not fail fast, it waits the full timeout and then blames the locator.
        """
        self.require_own_page()
        self.fill(self.sel("search_input"), term)
        self.click(self.sel("search_button"))

    def open_product_named(self, name: str) -> None:
        """Open a product's detail page via its 'View Product' link.

        The View Product links are a family (one per card), so we scope to the
        card that contains the product NAME and click the link inside it rather
        than indexing across a family that is doubled per card.
        """
        self.click_in_row(
            self.sel("product_cards"),
            name,
            self.sel("view_product_links"),
        )

    def view_cart_from_modal(self) -> None:
        """Click 'View Cart' inside the add-to-cart modal.

        This navigates away from the listing to the cart, so it does NOT
        confirm arrival on this page — the cart's own page object does that.
        """
        self.click(self.sel("view_cart_link_in_modal"))

    def continue_shopping_from_modal(self) -> None:
        """Dismiss the add-to-cart modal and stay on the listing.

        A scenario adding a second product must dismiss the modal first, or the
        next click lands on the overlay rather than the page underneath.
        """
        self.click(self.sel("continue_shopping_button"))

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the products listing is on screen. WAITS for it.

        Probes the All Products heading — the state-independent signal the page
        shows on a fresh (unsearched) load. Once a search has run this heading
        is replaced by the Searched Products heading, so is_search_executed()
        is the reader to use after searching.
        """
        return self.is_showing(self.sel("all_products_heading"), timeout_ms=timeout_ms)

    def is_search_executed(self, timeout_ms: Optional[int] = None) -> bool:
        """True once a search has actually run. WAITS for the results heading.

        The 'Searched Products' heading is the ONLY reliable signal that the
        search executed — a result count alone cannot tell 'returned one
        product' from 'never searched and still showing the full catalogue'.
        Call this only where a search IS expected to have run; it waits and
        times out otherwise.
        """
        return self.is_showing(self.sel("searched_products_heading"), timeout_ms=timeout_ms)

    def get_result_names(self) -> list[str]:
        """Every product name shown in the results, as a list of strings.

        The product-name family is doubled per card (card + hover overlay), so
        a name may appear more than once — assert membership with `in`, not an
        exact count.
        """
        return self.get_all_texts(self.sel("product_names"))

    def has_product_named(self, name: str) -> bool:
        """True once a result card for `name` is present. WAITS for it.

        Waits for at least one product card carrying the text, so it is safe to
        call immediately after a search while the results are still settling.
        Call this only where the product IS expected; it times out otherwise.
        """
        self.wait_for_row(self.sel("product_cards"), name, present=True)
        return True

    def get_result_card_count(self) -> int:
        """Number of product result CARDS currently displayed.

        Reads the un-doubled card family (one per product), NOT the doubled
        name/button families. A search matching nothing renders no cards and no
        empty-state text, so zero here is how absence of results is proven.
        Snapshot with no wait — use for asserting an exact/zero count after the
        search has already been confirmed to have executed.
        """
        return self.get_count(self.sel("product_cards"))
