"""
ProductsPage — the /products listing.

Search the catalogue, inspect the results, and open a product via its
View Product link. Selectors: see `pages.products` in the app inventory.

App: https://automationexercise.com
"""
from typing import List

from pages.base_page import BasePage


class ProductsPage(BasePage):
    """The All Products / search listing.

    The listing has two heading states: `all_products_heading` on the
    unsearched catalogue and `searched_products_heading` once a search has run.
    A search matching nothing renders NO cards and no empty-state text, so
    absence is asserted by counting cards, not by looking for a message.

    Several element families here match more than one element, and two of them
    (product_names, add_to_cart_buttons) render TWICE per card. Read the name
    family with get_all_texts(); open a product via its exact View Product href
    scoped to the card, never by indexing a doubled family.
    """

    INVENTORY_PAGE = "products"

    # ── actions ──────────────────────────────────────────────
    def open_listing(self, base_url: str) -> None:
        """Navigate directly to the All Products listing."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    def search_for(self, term: str) -> None:
        """Type a search term and submit; the results render on this page."""
        self.fill(self.sel("search_input"), term)
        self.click(self.sel("search_button"))
        self.wait_visible(self.sel("searched_products_heading"))

    def open_product(self, product_name: str) -> None:
        """Open a product's detail page via the View Product link on its card.

        Scoped to the card containing the product name, so it never touches a
        doubled family by index. Confirms the browser reached the listing state
        before clicking, in case an ad interstitial ate the search navigation.
        """
        self.click_in_row(
            self.sel("product_cards"),
            product_name,
            self.sel("view_product_links"),
        )

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self) -> bool:
        """True once the listing search box is on screen. WAITS for it.

        Probes `search_input` because it survives both heading states: the
        All Products heading is replaced by the Searched Products heading once
        a search runs, but the search box is present the whole time.
        """
        return self.is_showing(self.sel("search_input"))

    def has_searched(self) -> bool:
        """True once a search has executed, WAITING for the searched heading.

        The only reliable signal that the search ran — a result count alone
        cannot distinguish 'returned one product' from 'never ran, full
        catalogue still shown'.
        """
        return self.is_showing(self.sel("searched_products_heading"))

    def get_result_names(self) -> List[str]:
        """Visible product names in the current results, in DOM order.

        The name family is doubled per card, so callers asserting membership
        should use `in` rather than assuming a one-per-product list.
        """
        return self.get_all_texts(self.sel("product_names"))

    def has_result(self, product_name: str) -> bool:
        """True if a product with this name appears in the results.

        Waits for the card to be present, so it is safe to call immediately
        after a search.
        """
        self.wait_for_row(self.sel("product_cards"), product_name, present=True)
        return True

    def get_result_card_count(self) -> int:
        """Number of product cards currently in the results.

        A no-match search renders zero cards and no empty-state text, so this
        is how an empty result set is asserted on this page.
        """
        return self.get_count(self.sel("product_cards"))

    def assert_result_card_count(self, expected: int) -> None:
        """Wait until exactly `expected` product cards are shown."""
        self.wait_for_count(self.sel("product_cards"), expected)
