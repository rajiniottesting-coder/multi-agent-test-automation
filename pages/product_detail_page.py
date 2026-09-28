"""
ProductDetailPage — a single product's details screen (/product_details/{id}).

New page object for the shopping-session feature. Conventions copied from
LoginPage (the reference page object):

  - SELECTORS COME FROM THE APP INVENTORY. INVENTORY_PAGE names the page key,
    then every selector is looked up with self.sel("<element key>"). No literal
    selector strings live in this file.
  - methods are business verbs that say WHAT they act on (add_to_cart,
    view_cart_from_modal), never bare verbs.
  - every method uses a BasePage helper; no raw self.page.* calls.
  - no assertions here — those belong in step definitions.

The page is reached by clicking a product's "View Product" link on the listing,
so the browser is already here by the time these methods run.

App: https://automationexercise.com
"""
from typing import Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class ProductDetailPage(BasePage):
    """A single product's detail page. Selectors: see `pages.product_detail`
    in the app inventory.

    The URL is a template (/product_details/{product_id}), so this page is
    normally reached by clicking a listing's View Product link rather than by
    inventing an id here.
    """

    INVENTORY_PAGE = "product_detail"

    # ── actions ──────────────────────────────────────────────
    def add_to_cart(self) -> None:
        """Click this product's single Add to cart button.

        Unlike the listing page's family of add-to-cart controls, this page has
        exactly one, so it can be clicked directly. Clicking it opens a modal
        rather than navigating.
        """
        self.require_own_page()
        self.click(self.sel("add_to_cart_button"))

    def view_cart_from_modal(self) -> None:
        """From the add-to-cart modal, click View Cart to open the cart.

        The modal must already be showing (call add_to_cart first). This
        navigates away from the product page to /view_cart, so it does NOT
        confirm arrival on this page — the CartPage object owns that check.
        """
        self.wait_visible(self.sel("added_modal"))
        self.click(self.sel("view_cart_link_in_modal"))

    # ── queries ──────────────────────────────────────────────
    def product_name(self) -> str:
        """The product's displayed name. WAITS for it to be present."""
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))

    def is_added_modal_shown(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the 'added to cart' confirmation modal is on screen.

        WAITS for the modal and times out if it never appears, so call this
        only where the modal is the expected result — right after add_to_cart.
        """
        return self.is_showing(self.sel("added_modal"), timeout_ms=timeout_ms)
