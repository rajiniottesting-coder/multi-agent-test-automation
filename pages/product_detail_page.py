"""
ProductDetailPage — a single product's detail screen (/product_details/{id}).

New page object for the shopping-session feature. Exposes reading the product
name, adding the product to the cart, and leaving the add-to-cart modal via its
'View Cart' link.

Selectors come from `pages.product_detail` in the app inventory — never a
literal in this file. Methods are business verbs that name what they act on.

App: https://automationexercise.com
"""
from typing import Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class ProductDetailPage(BasePage):
    """One product's detail page. Selectors: see `pages.product_detail`.

    Reached by clicking a product's View Product link on the listing (the href
    already carries the product id), so this object rarely navigates directly.
    """

    INVENTORY_PAGE = "product_detail"

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the product name is on screen. WAITS for it.

        The product name is the most state-independent element on this page:
        the modal, review form and success message all come and go, but the
        name is present for every product in every state.
        """
        return self.is_showing(self.sel("product_name"), timeout_ms=timeout_ms)

    def product_name(self) -> str:
        """The product's name as rendered on the detail page. WAITS for it."""
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))

    # ── actions ──────────────────────────────────────────────
    def add_product_to_cart(self) -> None:
        """Click this product's single Add to cart control.

        Opens a modal rather than navigating; the modal blocks the page
        underneath until dismissed or followed to the cart.
        """
        self.require_own_page()
        self.click(self.sel("add_to_cart_button"))
        self.wait_visible(self.sel("added_modal"))

    def view_cart_from_modal(self) -> None:
        """Follow the add-to-cart modal's View Cart link to the cart page.

        Confirms the modal appeared first, then clicks through. Landing on the
        cart is confirmed by the CartPage object's own confirm_arrival().
        """
        self.wait_visible(self.sel("added_modal"))
        self.click(self.sel("view_cart_link_in_modal"))
