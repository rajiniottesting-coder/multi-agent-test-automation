"""
ProductDetailPage — a single product's detail page (/product_details/{id}).

New page object for the shopping-session feature. Responsibilities:
  - read the product name shown on this page
  - add THIS product to the cart (a unique control, unlike the listing's family)
  - leave the add-to-cart modal by navigating to the cart

Selectors come from `product_detail` in the app inventory; this file holds no
literal selector strings. App: https://automationexercise.com
"""
from typing import Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class ProductDetailPage(BasePage):
    """One product's detail page. Selectors: see `product_detail` in the inventory.

    Reached by clicking a product's View Product link on the listing (the href
    already carries the product id), so this object rarely navigates itself. The
    Add to cart control here is UNIQUE to this product — unlike the listing's
    family of 68 — which is why cart scenarios add from here.
    """

    INVENTORY_PAGE = "product_detail"

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the product name is on screen. WAITS for it.

        The product name heading is present in every state this page can be in,
        so it is a stable readiness signal.
        """
        return self.is_showing(self.sel("product_name"), timeout_ms=timeout_ms)

    def product_name(self) -> str:
        """The product's name as shown on this page. WAITS for it to appear."""
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))

    # ── actions ──────────────────────────────────────────────
    def add_product_to_cart(self) -> None:
        """Add THIS product to the cart, opening the add-to-cart modal.

        Confirms it is on this page first: filling/clicking a control that is
        not on screen does not fail fast — Playwright waits the full timeout and
        then blames the locator, which reads like a broken selector when the
        page is simply wrong.
        """
        self.require_own_page()
        self.click(self.sel("add_to_cart_button"))
        self.wait_visible(self.sel("added_modal"))

    def view_cart_from_modal(self) -> None:
        """From the add-to-cart modal, click View Cart to go to the cart page.

        The modal exists only after add_product_to_cart(); waiting for it here
        also proves the add succeeded. This method leaves this page, so it does
        not confirm arrival on THIS page — the cart page object confirms the
        cart on its own side.
        """
        self.wait_visible(self.sel("view_cart_link_in_modal"))
        self.click(self.sel("view_cart_link_in_modal"))
