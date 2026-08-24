"""
ProductDetailPage — a single product's detail screen (/product_details/{id}).

New page object for the shopping-session feature. Conventions follow the
LoginPage reference:

  - SELECTORS COME FROM THE APP INVENTORY. Set INVENTORY_PAGE, then look each
    element up by its `elements` KEY via self.sel("<key>"). No literal
    selector strings live in this file.
  - methods are business verbs that name WHAT they act on (add_to_cart,
    view_cart_from_modal), never bare verbs like open() or add().
  - every method uses a BasePage helper; no raw self.page.* calls.
  - no assertions here — those belong in step definitions.

The add-to-cart modal blocks the page underneath, so a scenario that adds a
product and then wants to stay on this page must dismiss it first
(dismiss_added_modal). A scenario that wants the cart uses
view_cart_from_modal, which also proves the modal appeared.

App: https://automationexercise.com
"""
from typing import Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class ProductDetailPage(BasePage):
    """One product's detail page. Selectors: see `product_detail` in the
    app inventory. The URL is a template (/product_details/{product_id}); the
    scenario reaches this page by clicking a listing's View Product link, so
    no product id is invented here."""

    INVENTORY_PAGE = "product_detail"

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the product name is on screen. WAITS for it.

        The inventory declares no dedicated `readiness` key for this page; the
        product name heading is the most state-independent element it lists —
        it is present in every state the detail page can be in, unlike the
        add-to-cart modal or the review-success message, which appear only
        after an interaction.
        """
        return self.is_showing(self.sel("product_name"), timeout_ms=timeout_ms)

    def get_product_name(self) -> str:
        """The displayed product name. WAITS for the heading to appear."""
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))

    # ── actions ──────────────────────────────────────────────
    def add_to_cart(self) -> None:
        """Click this product's single Add to cart control.

        Confirms it is ON this page first: filling/clicking a control that is
        not present does not fail fast — Playwright waits the full timeout and
        then blames the locator, which reads like a selector problem and is
        not one.
        """
        self.require_own_page()
        self.wait_visible(self.sel("add_to_cart_button"))
        self.click(self.sel("add_to_cart_button"))

    def view_cart_from_modal(self) -> None:
        """From the add-to-cart modal, click View Cart to go to the cart.

        Waits for the modal first, which also proves it appeared. Does NOT
        confirm arrival on this page — the click leaves for the cart, whose own
        page object confirms it.
        """
        self.wait_visible(self.sel("added_modal"))
        self.click(self.sel("view_cart_link_in_modal"))

    def dismiss_added_modal(self) -> None:
        """From the add-to-cart modal, click Continue Shopping to dismiss it
        and stay on this product. Needed before any further interaction with
        the page underneath, which the modal blocks."""
        self.wait_visible(self.sel("added_modal"))
        self.click(self.sel("continue_shopping_button"))
