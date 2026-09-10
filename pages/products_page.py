"""
ProductsPage — the Products listing (/products).

Search the catalogue, inspect result cards and open a product's detail page.

Selectors live in the app inventory under `pages.products`; this file names
them by KEY through self.sel(...) and never contains a literal selector. The
Products nav link belongs to the `nav` page, not this one, so reaching the
listing via the navigation is the NavPage's job — this page object only opens
the listing directly and works within it.

App: https://automationexercise.com
"""
from typing import Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class ProductsPage(BasePage):
    """Products listing. Selectors: see `pages.products` in the app inventory.

    Several selector families here are DOUBLED per card (product_names,
    add_to_cart_buttons render twice each). Never index across them: to act on
    one product, scope to the card containing its name, or open it via its
    View Product link whose href carries the product id.
    """

    INVENTORY_PAGE = "products"

    # ── actions ──────────────────────────────────────────────
    def open_listing(self, base_url: str) -> None:
        """Navigate directly to the Products listing page.

        Ends by confirming arrival on THIS page, so an ad interstitial that
        swallowed the navigation is recovered rather than blamed on the next
        step.
        """
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.confirm_arrival()

    def search_for(self, term: str) -> None:
        """Type a search term and submit it.

        Confirms it is on the listing first: filling the search box as an
        opening move from elsewhere would wait the full timeout and then
        report the box as a broken locator.
        """
        self.require_own_page()
        self.fill(self.sel("search_input"), term)
        self.click(self.sel("search_button"))
        # The searched-products heading is the only reliable signal that the
        # search EXECUTED — a result count alone cannot tell a one-hit search
        # from a search that never ran and still shows the full catalogue.
        self.wait_visible(self.sel("searched_products_heading"))

    def open_product(self, name: str) -> None:
        """Open the detail page for the product whose card carries `name`.

        Scopes to the card containing the name and clicks its View Product
        link, rather than indexing into the doubled product-name family.
        """
        self.require_own_page()
        self.click_in_row(
            self.sel("product_cards"),
            name,
            self.sel("view_product_links"),
        )

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the listing is on screen. WAITS for it.

        Probes the All Products heading — present on the unsearched listing,
        which is the state open_listing() lands in.
        """
        return self.is_showing(
            self.sel("all_products_heading"), timeout_ms=timeout_ms
        )

    def search_executed(self, timeout_ms: Optional[int] = None) -> bool:
        """True once a search has run. WAITS for the searched-products heading.

        Call this only where a search IS expected to have executed; it can
        answer 'no' only by exhausting its timeout.
        """
        return self.is_showing(
            self.sel("searched_products_heading"), timeout_ms=timeout_ms
        )

    def result_names(self) -> list[str]:
        """Every product name currently shown as a result card.

        The product-name family is doubled per card, so a name may appear
        twice — assert membership with `in`, not an exact count.
        """
        return self.get_all_texts(self.sel("product_names"))

    def has_result(self, name: str) -> bool:
        """True if a result card for `name` is present. WAITS for it.

        Call this only where the product IS expected to be found. To assert a
        search returned nothing, use get_result_card_count() instead — this
        waiting reader would time out rather than return False.
        """
        self.wait_for_row(self.sel("product_cards"), name, present=True)
        return True

    def get_result_card_count(self) -> int:
        """Number of result cards currently rendered.

        For asserting an EMPTY search result: this app renders NO cards for a
        no-match search (there is no empty-state message), so zero cards is
        the signal. Read after search_executed() confirms the search ran.
        """
        return self.get_count(self.sel("product_cards"))
