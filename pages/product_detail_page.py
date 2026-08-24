"""
ProductDetailPage — a single product's detail screen (/product_details/{id}).

New page object for the shopping-session feature. Its job:
  - confirm the product detail page has arrived and expose the product name
  - add THIS product to the cart (a single, unique control on this page,
    unlike the listing page's family of duplicated buttons)
  - handle the add-to-cart modal: View Cart or Continue Shopping

Conventions copied from pages/login_page.py:
  - selectors resolve through self.sel("<key>") against INVENTORY_PAGE
  - methods are business verbs that name WHAT they act on
  - every method uses a BasePage helper; no raw self.page.* calls
  - no assertions here — those belong in step definitions

App: https://automationexercise.com
"""
from typing import Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class ProductDetailPage(BasePage):
    """One product's detail page. Selectors: see `pages.product_detail`.

    The URL is a template (/product_details/{product_id}), so this page is
    normally reached by clicking a product's View Product link on the listing
    rather than by inventing an id. confirm_arrival() therefore compares
    against the template path from the inventory.
    """

    INVENTORY_PAGE = "product_detail"

    # ── queries ──────────────────────────────────────────────
    def product_detail_name(self) -> str:
        """Visible product name on the detail page. WAITS for it to appear.

        Call this to assert which product's page is showing. It waits, so it
        is for the presence case; there is no absence case for this element.
        """
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))

    def is_added_modal_shown(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the add-to-cart confirmation modal is on screen. WAITS.

        The modal does not exist until Add to cart is clicked, so call this
        only after adding a product. It waits and logs, so a step asserting
        the modal appeared gets a real signal rather than a race.
        """
        return self.is_showing(self.sel("added_modal"), timeout_ms=timeout_ms)

    # ── actions ──────────────────────────────────────────────
    def add_product_to_cart(self) -> None:
        """Click this product's single Add to cart control.

        Confirms it is ON this page first: clicking a control that is not
        there does not fail fast — Playwright waits the full timeout and then
        blames the locator, which reads like a selector fault and is not one.
        """
        self.require_own_page()
        self.click(self.sel("add_to_cart_button"))

    def view_cart_from_modal(self) -> None:
        """Click 'View Cart' inside the add-to-cart modal, going to the cart.

        Available only after a product has been added, since the modal does
        not exist before then. Landing on the cart is confirmed by the cart
        page object, not here — this method leaves this page.
        """
        self.wait_visible(self.sel("added_modal"))
        self.click(self.sel("view_cart_link_in_modal"))

    def continue_shopping_from_modal(self) -> None:
        """Dismiss the add-to-cart modal and stay on this product's page.

        The modal blocks the page underneath, so this must be called before
        any further interaction with the detail page.
        """
        self.wait_visible(self.sel("added_modal"))
        self.click(self.sel("continue_shopping_button"))
        self.wait_hidden(self.sel("added_modal"))
