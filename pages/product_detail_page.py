"""
ProductDetailPage — a single product's detail screen (/product_details/{id}).

New page object. Style copied from pages/login_page.py:

  - SELECTORS COME FROM THE APP INVENTORY, never a literal here. Set
    INVENTORY_PAGE, then use self.sel("<element_key>").
  - methods are business verbs that name WHAT they act on
    (open_product_by_id, add_displayed_product_to_cart), never bare verbs.
  - every method uses a BasePage helper; no raw self.page.* calls.
  - no assertions here — those belong in step definitions.

App: https://automationexercise.com
"""
from typing import Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class ProductDetailPage(BasePage):
    """A single product's detail page. Selectors: see `product_detail` in
    the app inventory.

    The URL is a TEMPLATE (/product_details/{product_id}) — one page per
    product. A scenario normally arrives here by clicking a product's
    View Product link on the listing, so the id never has to be invented.
    """

    INVENTORY_PAGE = "product_detail"

    # ── actions ──────────────────────────────────────────────
    def open_product_by_id(self, base_url: str, product_id: int) -> None:
        """Navigate directly to a product's detail page by its id.

        Args:
            base_url: application base URL, supplied by the `base_url` fixture.
            product_id: the numeric product id that fills the URL template.
        """
        self.navigate(f"{base_url.rstrip('/')}{self.page_url(product_id=product_id)}")

    def add_displayed_product_to_cart(self) -> None:
        """Add the product shown on this page to the cart.

        Confirms it is ON this page first: filling/clicking a control that is
        not there does not fail fast — Playwright waits the full timeout and
        then blames the locator, which reads like a broken selector when the
        page is simply wrong.

        This opens the add-to-cart MODAL rather than navigating. Leave the
        page via view_cart_from_modal() or continue_shopping().
        """
        self.require_own_page()
        self.click(self.sel("add_to_cart_button"))

    def view_cart_from_modal(self) -> None:
        """Click 'View Cart' inside the add-to-cart modal to go to the cart.

        The modal exists only after adding a product, so calling this before
        that will time out on the modal link.
        """
        self.wait_visible(self.sel("added_modal"))
        self.click(self.sel("view_cart_link_in_modal"))

    def continue_shopping(self) -> None:
        """Dismiss the add-to-cart modal and stay on this product page.

        The modal blocks the page underneath, so dismiss it before any further
        interaction with the page.
        """
        self.wait_visible(self.sel("added_modal"))
        self.click(self.sel("continue_shopping_button"))

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the product name is on screen. WAITS for it.

        The product name is the most state-independent element on this page —
        it is present whether or not the add-to-cart modal has been opened, so
        it is a reliable readiness probe.
        """
        return self.is_showing(self.sel("product_name"), timeout_ms=timeout_ms)

    def get_product_name(self) -> str:
        """The displayed product name. WAITS for it to appear.

        Use this to assert the correct product's detail page has loaded.
        """
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))
