"""
ProductDetailPage — a single product's detail screen (/product_details/{id}).

New page object for the shopping-session feature. Responsibilities:
  - read the product's name and price
  - add the product to the cart (opens a blocking modal)
  - navigate to the cart via that modal

Conventions (copied from pages/login_page.py, the reference page object):
  - SELECTORS COME FROM THE APP INVENTORY. Declare INVENTORY_PAGE and resolve
    every selector through self.sel("<key>"); never a literal selector here.
  - methods are business verbs that name what they act on
  - every method uses a BasePage helper; no raw self.page.* calls
  - no assertions here — those belong in the step definitions

App: https://automationexercise.com
"""
from typing import Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class ProductDetailPage(BasePage):
    """A single product's detail page. Selectors: see `pages.product_detail`
    in the app inventory.

    The URL is a TEMPLATE (/product_details/{product_id}) — one page per
    product. Prefer reaching this page by clicking a listing's View Product
    link, whose href already carries the id, rather than inventing an id here.
    """

    INVENTORY_PAGE = "product_detail"

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the product detail page is on screen. WAITS for it.

        Probes the product name element, which is present in every state of
        this page (the modal and review form are additive, not replacements).
        """
        return self.is_showing(self.sel("product_name"), timeout_ms=timeout_ms)

    def product_name(self) -> str:
        """The product's name. WAITS for it to appear."""
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))

    def product_price(self) -> str:
        """The product's price text, e.g. 'Rs. 500'. WAITS for it.

        Rendered with a currency prefix — assert on the number it contains,
        not on the exact format.
        """
        self.wait_visible(self.sel("product_price"))
        return self.get_text(self.sel("product_price"))

    # ── actions ──────────────────────────────────────────────
    def add_to_cart(self) -> None:
        """Add THIS product to the cart.

        Confirms the browser is on this page first: clicking Add to cart from
        elsewhere would wait the full timeout and then blame the button's
        locator rather than the wrong page. Waits for the resulting modal so
        callers can immediately act on it.
        """
        self.require_own_page()
        self.click(self.sel("add_to_cart_button"))
        self.wait_visible(self.sel("added_modal"))

    def view_cart_from_modal(self) -> None:
        """Click 'View Cart' in the add-to-cart modal to go to the cart.

        The modal exists only after add_to_cart() has been clicked. This
        leaves THIS page for /view_cart, so it does not confirm arrival here —
        the cart page object is responsible for confirming it landed there.
        """
        self.wait_visible(self.sel("view_cart_link_in_modal"))
        self.click(self.sel("view_cart_link_in_modal"))

    def continue_shopping(self) -> None:
        """Dismiss the add-to-cart modal and stay on this product page.

        The modal blocks the page underneath, so this must be called before
        any further interaction with the page when the cart is not the next
        destination.
        """
        self.wait_visible(self.sel("continue_shopping_button"))
        self.click(self.sel("continue_shopping_button"))
