"""
ProductDetailPage — a single product's detail page (/product_details/{id}).

New page object for the cart-add-remove feature. Provides:
  - opening a named product's detail page by clicking its listing link
  - adding the product to the cart
  - dismissing the add-to-cart modal (Continue Shopping)
  - navigating to the cart from the modal (View Cart)

Selectors come from the `product_detail` and `products` pages in the app
inventory. This class drives the detail page itself; reaching it starts from
the products listing, so a couple of methods resolve listing keys to click
the right 'View Product' link.

App: https://automationexercise.com
"""
from typing import Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class ProductDetailPage(BasePage):
    """A product's detail page. Selectors: see `product_detail` in the inventory.

    Opening the page goes through the products LISTING, because the listing's
    View Product link already carries the product id in its href — the test
    never has to invent one. For that single navigation the method resolves the
    listing's own inventory keys; everything after landing uses this page's keys.
    """

    INVENTORY_PAGE = "product_detail"

    # Keys on the products listing page, needed only to click into a product.
    _PRODUCTS_PAGE = "products"
    _PRODUCTS_CARD_FAMILY = "product_cards"
    _PRODUCTS_VIEW_LINK_FAMILY = "view_product_links"
    _PRODUCTS_NAME_FAMILY = "product_names"

    # ── navigation ───────────────────────────────────────────
    def open_product(self, product_name: str) -> None:
        """Open the detail page for a named product from the listing.

        Starts on the products listing (requiring it first so a stray call
        fails fast rather than timing out on a missing card), finds the card
        whose text contains the product name, and clicks the View Product link
        inside that card. Confirms arrival on THIS detail page afterwards — a
        click that is eaten by an ad interstitial reports success but does not
        move, so confirm_arrival re-issues the navigation if needed.
        """
        self.require_own_page_on(self._PRODUCTS_PAGE)
        self.click_in_row(
            self._products_sel(self._PRODUCTS_CARD_FAMILY),
            product_name,
            self._products_sel(self._PRODUCTS_VIEW_LINK_FAMILY),
        )
        self.confirm_arrival()

    # ── actions ──────────────────────────────────────────────
    def add_to_cart(self) -> None:
        """Click this product's single Add to cart button.

        Confirms it is on this page first. Unlike the listing page, this page
        has exactly one add-to-cart control, so the click is unambiguous.
        """
        self.require_own_page()
        self.click(self.sel("add_to_cart_button"))
        self.wait_visible(self.sel("added_modal"))

    def continue_shopping(self) -> None:
        """Dismiss the add-to-cart modal and stay on this product page.

        The modal blocks the page underneath, so this must be called before any
        further interaction with the detail page (e.g. adding the product a
        second time).
        """
        self.wait_visible(self.sel("continue_shopping_button"))
        self.click(self.sel("continue_shopping_button"))
        self.wait_hidden(self.sel("added_modal"))

    def view_cart_from_modal(self) -> None:
        """Click View Cart inside the add-to-cart modal.

        Navigates to /view_cart. Preferred over the nav Cart link right after
        adding, because it also proves the modal appeared.
        """
        self.wait_visible(self.sel("view_cart_link_in_modal"))
        self.click(self.sel("view_cart_link_in_modal"))

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the product detail page is on screen. WAITS for it.

        Probes the product name element in the product-information block, which
        is present in every state this page can be in.
        """
        return self.is_showing(self.sel("product_name"), timeout_ms=timeout_ms)

    def product_name(self) -> str:
        """The displayed product name from the product-information block."""
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))

    def is_modal_showing(self) -> bool:
        """True once the add-to-cart modal is visible. WAITS for it.

        Call this only where the modal is expected. It answers 'no' only by
        timing out, so do not use it to branch on optional state.
        """
        return self.is_showing(self.sel("added_modal"))

    # ── internal helpers ─────────────────────────────────────
    def _products_sel(self, key: str) -> str:
        """Resolve a selector key on the PRODUCTS listing page.

        open_product clicks into a product from the listing, so it needs a
        handful of that page's keys. This keeps those lookups explicit rather
        than guessing listing selectors here.
        """
        return self.sel_on(self._PRODUCTS_PAGE, key)
