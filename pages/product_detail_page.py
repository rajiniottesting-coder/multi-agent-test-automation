"""
ProductDetailPage — a single product's detail screen at /product_details/{id}.

New page object for the shopping-session feature. Responsibilities:
  - read the displayed product name
  - add the product to the cart
  - leave the add-to-cart confirmation modal via View Cart

Conventions (copied from LoginPage, the gold-standard reference):
  - SELECTORS COME FROM THE APP INVENTORY. Set INVENTORY_PAGE, then use
    self.sel("<element key>"); never a literal selector string.
  - methods are business verbs that name WHAT they act on (open_product,
    add_to_cart), never bare verbs.
  - every method uses a BasePage helper; no raw self.page.* calls.
  - no assertions here — those belong in step definitions.

App: https://automationexercise.com
"""
from typing import Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class ProductDetailPage(BasePage):
    """Product detail screen. Selectors: see `pages.product_detail` in the inventory.

    The URL is a TEMPLATE (/product_details/{product_id}); one page per product.
    Prefer reaching it by clicking a listing's View Product link — that href
    already carries the id — rather than inventing an id here.
    """

    INVENTORY_PAGE = "product_detail"

    # ── actions ──────────────────────────────────────────────
    def open_product(self, base_url: str, product_id: int) -> None:
        """Navigate directly to a product's detail page by id.

        Args:
            base_url: application base URL from the `base_url` fixture.
            product_id: the numeric product id used in the URL template.
        """
        self.navigate(f"{base_url.rstrip('/')}{self.page_url(product_id=product_id)}")

    def add_to_cart(self) -> None:
        """Click Add to cart for THIS product, opening the confirmation modal.

        Confirms it is ON this page first: filling/clicking a control that is
        not present does not fail fast — Playwright waits the full timeout and
        then blames the locator, which reads like a broken selector when the
        page is simply wrong. This is a precondition, so it RAISES rather than
        silently navigating.
        """
        self.require_own_page()
        self.click(self.sel("add_to_cart_button"))

    def go_to_cart_from_modal(self) -> None:
        """Leave the add-to-cart modal via its View Cart link, landing on the cart.

        Waits for the modal to appear first, because it opens asynchronously
        after the Add to cart click rather than navigating. The click leaves
        this page, so no confirm_arrival() here — the destination's own page
        object confirms arrival on the cart.
        """
        self.wait_visible(self.sel("added_modal"))
        self.click(self.sel("view_cart_link_in_modal"))

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the product name heading is on screen. WAITS for it.

        There is no `readiness` key on this inventory page, so this probes the
        product name heading — the most state-independent element here: it is
        present on every product's detail page regardless of the add-to-cart
        modal or review state, both of which are conditional.
        """
        return self.is_showing(self.sel("product_name"), timeout_ms=timeout_ms)

    def get_product_name(self) -> str:
        """Return the displayed product name. WAITS for the heading first.

        The heading is what the scenario asserts against ('the product detail
        page should show "Blue Top"'), so this is a waiting presence reader.
        """
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))

    def has_added_confirmation(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the add-to-cart confirmation modal is showing. WAITS.

        Call this only where the confirmation IS expected — it is a waiting
        reader, so it answers 'no' only by exhausting its timeout.
        """
        return self.is_showing(self.sel("added_modal"), timeout_ms=timeout_ms)
