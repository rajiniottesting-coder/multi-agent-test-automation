"""
ProductDetailPage — a single product's detail screen (/product_details/{id}).

New page object for the shopping-session feature. Responsibilities:
  - read the product name shown on this page
  - add THIS product to the cart (opens a modal rather than navigating)
  - leave the add-to-cart modal for the cart page

Conventions copied from pages/login_page.py:
  - selectors come from the app inventory via self.sel("<key>"); never a
    literal selector string in this file
  - methods are business verbs that name what they act on
  - no assertions here — those belong in step definitions
  - a method that clicks its way to another page confirms arrival there

App: https://automationexercise.com
"""
from typing import Optional

import logging

from pages.base_page import BasePage
from pages.cart_page import CartPage


logger = logging.getLogger(__name__)


class ProductDetailPage(BasePage):
    """Product detail. Selectors: see `product_detail` in the app inventory.

    The URL is a TEMPLATE (one page per product), so this page is normally
    reached by clicking a product's View Product link on the listing — that
    href already carries the id, so the test never invents one.
    """

    INVENTORY_PAGE = "product_detail"

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the product name is on screen. WAITS for it.

        The product name is present in every state this page can be in, which
        makes it a stable readiness signal (the add-to-cart modal and review
        controls come and go, so they are not).
        """
        return self.is_showing(self.sel("product_name"), timeout_ms=timeout_ms)

    def product_name(self) -> str:
        """The product name shown on this detail page. WAITS for it.

        Only call this when the detail page is expected to be loaded — it waits
        for the name element before reading, so it raises on absence rather
        than returning an empty string.
        """
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))

    # ── actions ──────────────────────────────────────────────
    def add_product_to_cart(self) -> None:
        """Click Add to cart for THIS product and wait for the modal.

        Adding to cart opens a MODAL rather than navigating, so this waits for
        that modal to confirm the add registered. The single add-to-cart
        control on this page is unique (unlike the listing's family of 68),
        so it is safe to click directly.
        """
        self.require_own_page()
        self.click(self.sel("add_to_cart_button"))
        self.wait_visible(self.sel("added_modal"))

    def view_cart_from_modal(self) -> CartPage:
        """Click View Cart inside the add-to-cart modal, landing on the cart.

        Prefer this over the nav Cart link when a product has just been added:
        clicking it also proves the modal appeared. Confirms arrival on the
        cart page and returns its page object so the caller can act on it.
        """
        self.wait_visible(self.sel("view_cart_link_in_modal"))
        self.click(self.sel("view_cart_link_in_modal"))
        cart_page = CartPage(self.page)
        cart_page.confirm_arrival()
        return cart_page

    def continue_shopping(self) -> None:
        """Dismiss the add-to-cart modal and stay on this product page.

        The modal blocks the page underneath, so this must be called before any
        further interaction with the detail page after an add.
        """
        self.wait_visible(self.sel("continue_shopping_button"))
        self.click(self.sel("continue_shopping_button"))
        self.wait_hidden(self.sel("added_modal"))
