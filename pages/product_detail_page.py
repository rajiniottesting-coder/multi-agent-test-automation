"""
ProductDetailPage — a single product's detail screen (/product_details/{id}).

New page object for the shopping-session feature. Conventions follow
pages/login_page.py:

  - SELECTORS COME FROM THE APP INVENTORY. Declare INVENTORY_PAGE, then use
    self.sel("<element_key>"); never a literal selector string here.
  - methods are business verbs that say WHAT they act on (open_product,
    add_product_to_cart), never bare verbs.
  - every method uses a BasePage helper; no raw self.page.* calls.
  - no assertions here — those belong in the step definitions.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class ProductDetailPage(BasePage):
    """One product's detail page. Selectors: see `pages.product_detail`
    in the app inventory.

    The URL is a TEMPLATE (/product_details/{product_id}), so this page is
    reached either by clicking a listing's View Product link — which already
    carries the id — or by open_product(base_url, product_id). Adding to cart
    opens a MODAL rather than navigating; it blocks the page underneath, so a
    scenario adding a second product must dismiss it first.
    """

    INVENTORY_PAGE = "product_detail"

    # ── actions ──────────────────────────────────────────────
    def open_product(self, base_url: str, product_id: int) -> None:
        """Navigate directly to a product's detail page by its id.

        Prefer reaching this page via the listing's View Product link, which
        already carries the id; use this only when the test starts here.
        """
        path = self.page_url(product_id=product_id)
        self.navigate(f"{base_url.rstrip('/')}{path}")
        self.confirm_arrival(product_id=product_id)

    def add_product_to_cart(self) -> None:
        """Click Add to cart for THIS product, opening the confirmation modal.

        Unlike the listing page's family of buttons, this control is unique to
        the product, so no scoping is required.
        """
        self.click(self.sel("add_to_cart_button"))
        self.wait_visible(self.sel("added_modal"))

    def go_to_cart_from_modal(self) -> None:
        """Follow the View Cart link inside the add-to-cart modal.

        Also proves the modal appeared: the link exists only within it.
        """
        self.click(self.sel("view_cart_link_in_modal"))

    def continue_shopping(self) -> None:
        """Dismiss the add-to-cart modal and stay on this product page.

        Needed before any further interaction with the page underneath,
        because the modal blocks it.
        """
        self.click(self.sel("continue_shopping_button"))

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the product name is on screen. WAITS for it.

        The product name is present in every state this page can be in, which
        makes it a reliable readiness signal (the modal and review-success
        elements appear only after an interaction).
        """
        return self.is_showing(self.sel("product_name"), timeout_ms=timeout_ms)

    def product_name(self) -> str:
        """The product's display name. WAITS for it to appear."""
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))

    def is_modal_showing(self) -> bool:
        """True once the add-to-cart modal is visible. WAITS for it.

        Call this only where the modal IS expected — it is the waiting form,
        so it can answer 'no' only by timing out.
        """
        return self.is_showing(self.sel("added_modal"))
