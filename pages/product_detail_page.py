"""
ProductDetailPage — a single product's detail screen (/product_details/{id}).

New page object for the cart-management feature. Conventions copied from the
LoginPage reference:

  - selectors come from the app inventory via self.sel("<key>"); no literals
  - methods are business verbs that name WHAT they act on
  - every method uses a BasePage helper; no raw self.page.* calls
  - no assertions here — those belong in step definitions

The add-to-cart flow opens a MODAL rather than navigating. The modal blocks the
page underneath, so a scenario adding the same product twice MUST dismiss it via
continue_shopping() before the second Add to cart, or the click lands on the
overlay.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class ProductDetailPage(BasePage):
    """A product's detail page. Selectors: see `product_detail` in the inventory."""

    INVENTORY_PAGE = "product_detail"

    # ── navigation ───────────────────────────────────────────
    def open_product(self, base_url: str, product_id: int) -> None:
        """Navigate directly to a product's detail page by its id.

        Prefer reaching this page by clicking a product's View Product link on
        the listing — that href already carries the id — but this is available
        when a test knows the id up front.
        """
        self.navigate(f"{base_url.rstrip('/')}{self.page_url(product_id=product_id)}")

    def confirm_arrival(self, **params: object) -> None:
        """Confirm the browser reached a product detail page, recovering if not.

        Overrides BasePage only to key off the product name element, which is
        the most state-independent thing on this page.
        """
        self.wait_visible(self.sel("product_name"))

    # ── actions ──────────────────────────────────────────────
    def set_quantity(self, quantity: int) -> None:
        """Set the desired quantity BEFORE adding to cart.

        Changing the quantity after the product is in the cart has no effect,
        so this must be called ahead of add_to_cart().
        """
        self.fill(self.sel("quantity_input"), str(quantity))

    def add_to_cart(self) -> None:
        """Click Add to cart for THIS product, opening the confirmation modal."""
        self.click(self.sel("add_to_cart_button"))

    def go_to_cart_from_modal(self) -> None:
        """Click View Cart inside the add-to-cart modal, navigating to the cart.

        Waits for the modal first so the click cannot race the modal open.
        """
        self.wait_visible(self.sel("added_modal"))
        self.click(self.sel("view_cart_link_in_modal"))

    def continue_shopping(self) -> None:
        """Dismiss the add-to-cart modal and stay on this product page.

        Required before any further interaction with the page underneath — the
        modal blocks it — and before adding the same product a second time.
        """
        self.wait_visible(self.sel("added_modal"))
        self.click(self.sel("continue_shopping_button"))

    # ── queries ──────────────────────────────────────────────
    def product_detail_name(self) -> str:
        """The product name shown in the product-information panel. WAITS for it."""
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))

    def product_detail_price(self) -> str:
        """The product price, rendered as 'Rs. 500'. WAITS for it.

        Assert on the number, not the format.
        """
        self.wait_visible(self.sel("product_price"))
        return self.get_text(self.sel("product_price"))

    def is_added_modal_showing(self) -> bool:
        """True once the add-to-cart confirmation modal is visible. WAITS for it.

        Call this only where the modal is EXPECTED — it times out if the modal
        never appears rather than returning False.
        """
        return self.is_showing(self.sel("added_modal"))

    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the product detail page is on screen. WAITS for it.

        Keys off the product name, which survives every state this page can be
        in — the add-to-cart modal opens on top of it rather than replacing it.
        """
        return self.is_showing(self.sel("product_name"), timeout_ms=timeout_ms)
