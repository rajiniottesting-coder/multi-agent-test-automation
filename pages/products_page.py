"""
ProductsPage — the Products / search listing (/products).

Selectors come from `pages.products` in the app inventory; every one is
resolved through self.sel("<key>"). No literal selectors live in this file.

Key behaviours captured from the inventory notes:
  - The families product_cards / product_names / add_to_cart_buttons /
    view_product_links match MANY elements, and product_names /
    add_to_cart_buttons are DOUBLED per card. They are read with the plural
    helpers only; to act on ONE product we scope by the product name.
  - An empty search returns the WHOLE catalogue; a non-matching search
    renders NO cards (there is no explicit empty-state message here), so
    absence is asserted by counting cards, not by looking for text.
  - searched_products_heading is the only reliable signal that a search
    actually EXECUTED, so is_search_executed() waits on it.

App: https://automationexercise.com
"""
from typing import Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class ProductsPage(BasePage):
    """Products / search listing. Selectors: see `pages.products` in the inventory."""

    INVENTORY_PAGE = "products"

    # ── navigation ───────────────────────────────────────────
    def open_products(self, base_url: str) -> None:
        """Navigate to the Products listing.

        Args:
            base_url: application base URL from the `base_url` fixture. The path
                      comes from the inventory, so it is not duplicated here.
        """
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.confirm_arrival()

    # ── actions ──────────────────────────────────────────────
    def search_for(self, term: str) -> None:
        """Enter a search term and submit.

        Confirms it is ON this page before filling — a fill from elsewhere
        would wait the full timeout and then blame the search field rather than
        the wrong page. An empty term is legal and returns the full catalogue.
        """
        self.require_own_page()
        self.fill(self.sel("search_input"), term)
        self.click(self.sel("search_button"))

    def view_product(self, product_name: str) -> None:
        """Open the detail page for the product whose card contains `product_name`.

        Scopes to the card that contains the name and clicks its View Product
        link, rather than indexing across the doubled families. Confirmation
        that the detail page loaded belongs to ProductDetailPage.
        """
        self.click_in_row(
            self.sel("product_cards"),
            product_name,
            self.sel("view_product_links"),
        )

    def view_cart_from_modal(self) -> None:
        """Click 'View Cart' inside the add-to-cart modal, navigating to the cart.

        The modal appears only after a product is added; arriving-page
        confirmation belongs to CartPage, so this method only clicks.
        """
        self.wait_visible(self.sel("added_modal"))
        self.click(self.sel("view_cart_link_in_modal"))

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the products listing is on screen. WAITS for it.

        Probes the All Products heading, which is present on the unsearched
        listing that open_products() lands on.
        """
        return self.is_showing(self.sel("all_products_heading"), timeout_ms=timeout_ms)

    def is_search_executed(self, timeout_ms: Optional[int] = None) -> bool:
        """True once a search has run. WAITS, and times out if it never runs.

        Backed by searched_products_heading, the only signal that distinguishes
        'the search returned results' from 'the search never ran and the full
        catalogue is still showing'. Call this only where a search IS expected
        to have executed.
        """
        return self.is_showing(self.sel("searched_products_heading"), timeout_ms=timeout_ms)

    def get_result_names(self) -> list[str]:
        """Return the visible product names in the results, in DOM order.

        Reads the DOUBLED product_names family, so each product name appears
        more than once. Callers asserting presence should use containment or
        `has_result` rather than assuming a unique index.
        """
        return self.get_all_texts(self.sel("product_names"))

    def has_result(self, product_name: str) -> bool:
        """True if a product card whose name contains `product_name` is shown.

        WAITS for at least one result card, then checks membership — for use
        where the product IS expected to appear.
        """
        self.wait_for_any(self.sel("product_cards"))
        return any(product_name in name for name in self.get_result_names())

    def get_result_count(self) -> int:
        """Return the number of product result cards currently rendered.

        product_cards is one-per-card (NOT doubled), so this is a true card
        count. A snapshot with no waiting — appropriate for asserting an EMPTY
        result set, where there is nothing to wait for and the expected count
        is zero.
        """
        return self.get_count(self.sel("product_cards"))
