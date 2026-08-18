"""
ProductsPage — the all-products listing, with search and category browsing.

App: https://automationexercise.com
"""
from typing import List, Optional

from pages.base_page import BasePage


class ProductsPage(BasePage):
    """All products. Selectors: see `pages.products` in the app inventory.

    EVERY CARD IS A FAMILY. Each product renders its name, price and Add to
    cart control twice — once in the card body, once in the hover overlay —
    so `add_to_cart_buttons` matches 68 elements on this page, not 34. Those
    keys are declared under `multi_match` in the inventory and are read with
    the plural helpers only; acting on one product goes through its own View
    Product link, whose href carries the product id.
    """

    INVENTORY_PAGE = "products"

    # ── actions ──────────────────────────────────────────────
    def open_listing(self, base_url: str) -> None:
        """Navigate to the all-products page."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    def search(self, term: str) -> None:
        """Search by product name and submit.

        The results replace the listing on the same page — this is a full
        page load, not an in-place filter.
        """
        self.fill(self.sel("search_input"), term)
        self.click(self.sel("search_button"))

    def open_product(self, name: str) -> None:
        """Open one product's detail page by its visible name.

        Addresses the product BY TEXT rather than by index: the listing order
        is the site owner's, not ours, and an index silently points at a
        different product the moment the catalogue is reordered.

        The name is matched against the product-name family, and the SAME
        position is then used on the view-link family - the two run in
        lockstep, one per card. It cannot use the link's accessible name:
        elements_notes on view_product_links records that a role+name locator
        for these links resolved to ZERO against the live page, because icon
        markup inside the anchor pollutes the computed name.
        """
        index = self.find_row_index_by_text(self.sel("product_names"), name)
        self.click_nth(self.sel("view_product_links"), index)

    def dismiss_added_modal(self) -> None:
        """Close the 'added to cart' modal and stay on the listing.

        Adding to cart opens a MODAL rather than navigating, and it blocks the
        page underneath. A scenario that adds two products must call this
        between them, or the second click lands on the overlay and fails with
        'intercepts pointer events'.
        """
        self.click(self.sel("continue_shopping_button"))

    def view_cart_from_modal(self) -> None:
        """Follow the modal's View Cart link."""
        self.click(self.sel("view_cart_link_in_modal"))

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the listing is on screen. WAITS for it."""
        return self.is_showing(self.sel("all_products_heading"),
                               timeout_ms=timeout_ms)

    def product_names(self) -> List[str]:
        """Every product name currently listed, in DOM order.

        A plural read of a `multi_match` key, which is the only legal way to
        touch one. Names appear twice per card, so expect duplicates — assert
        that a name IS present rather than counting entries.
        """
        return self.get_all_texts(self.sel("product_names"))

    def has_product(self, name: str) -> bool:
        """True if a product with this name is listed."""
        return any(name.lower() in t.lower() for t in self.product_names())

    def result_count(self) -> int:
        """Number of product cards currently listed.

        A search matching nothing renders NO cards rather than an empty-state
        message, so zero here is how absence is asserted on this page.
        """
        return self.get_count(self.sel("product_cards"))

    def has_added_modal(self) -> bool:
        """True if the 'added to cart' modal is showing. Never waits."""
        return self.is_visible(self.sel("added_modal"))