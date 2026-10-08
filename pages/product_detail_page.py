"""
ProductDetailPage — a single product's detail screen (/product_details/{id}).

New page object for the shopping-session feature. Supports:
  - reading the product name shown on the page
  - adding the product to the cart (opens a modal, does not navigate)
  - leaving the add-to-cart modal via its 'View Cart' link

Conventions (copied from pages/login_page.py):
  - SELECTORS COME FROM THE APP INVENTORY, never a literal here. Declare
    INVENTORY_PAGE, then self.sel("<element_key>").
  - methods are business verbs that name WHAT they act on (open_product,
    add_to_cart), not bare verbs.
  - every method uses a BasePage helper; no raw self.page.* calls.
  - no assertions here — those belong in step definitions.

App: https://automationexercise.com
"""
from typing import Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class ProductDetailPage(BasePage):
    """One product's detail page. Selectors: see `product_detail` in the inventory.

    The URL is a template (/product_details/{product_id}), one page per product.
    Scenarios reach it by clicking a product's View Product link on the listing,
    so the id never has to be invented here.
    """

    INVENTORY_PAGE = "product_detail"

    # ── actions ──────────────────────────────────────────────
    def open_product(self, base_url: str, product_id: int) -> None:
        """Navigate directly to a product's detail page by its id.

        Args:
            base_url: application base URL from the `base_url` fixture.
            product_id: numeric product id used in the URL template.
        """
        self.navigate(f"{base_url.rstrip('/')}{self.page_url(product_id=product_id)}")

    def add_to_cart(self) -> None:
        """Click this product's single Add to cart control.

        This opens a MODAL rather than navigating. The modal blocks the page
        underneath, so a scenario doing anything further must leave it first
        (view_cart_from_modal here, or a continue-shopping control).
        """
        self.require_own_page()
        self.click(self.sel("add_to_cart_button"))
        self.wait_visible(self.sel("added_modal"))

    def view_cart_from_modal(self) -> None:
        """Click 'View Cart' inside the add-to-cart modal and go to the cart.

        The modal must already be open (add_to_cart was called). This navigates
        to /view_cart, so the cart page object confirms arrival.
        """
        self.wait_visible(self.sel("view_cart_link_in_modal"))
        self.click(self.sel("view_cart_link_in_modal"))

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the product detail page is on screen. WAITS for it.

        Probes the product name element, which is present whenever the detail
        page has rendered for any product.
        """
        return self.is_showing(self.sel("product_name"), timeout_ms=timeout_ms)

    def product_name(self) -> str:
        """The product name shown on this page. WAITS for it to appear."""
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))

    def is_modal_shown(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the add-to-cart modal is on screen. WAITS, times out if not.

        Call this only where the modal is expected. Confirms add_to_cart
        succeeded before leaving the page.
        """
        return self.is_showing(self.sel("added_modal"), timeout_ms=timeout_ms)
