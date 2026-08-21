"""
ProductDetailPage — a single product's detail screen (/product_details/{id}).

New page object for the cart-management feature. Conventions follow
pages/login_page.py:

  - SELECTORS COME FROM THE APP INVENTORY. INVENTORY_PAGE names the page key,
    then every element is looked up with self.sel("<key>"). No literal
    selector strings live in this file.
  - methods are business verbs that say WHAT they act on (add_product_to_cart,
    open_cart_from_modal), never bare verbs that would collide with each other.
  - every method uses a BasePage helper; no raw self.page.* calls.
  - no assertions here — those belong in step definitions.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class ProductDetailPage(BasePage):
    """A product's detail page. Selectors: see `product_detail` in the inventory.

    Reached by clicking a product's View Product link on the listing, which
    already carries the product id in its href, so this page never invents one.
    Adding to cart opens a MODAL that blocks the page underneath; a scenario
    that adds twice must dismiss the modal between adds via
    continue_shopping().
    """

    INVENTORY_PAGE = "product_detail"

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the product name heading is on screen. WAITS for it.

        The product name is present in every state this page can be in, so it
        is a stable readiness signal.
        """
        return self.is_showing(self.sel("product_name"), timeout_ms=timeout_ms)

    def product_name(self) -> str:
        """Visible name of the product being viewed."""
        return self.get_text(self.sel("product_name"))

    def product_price(self) -> str:
        """Visible price of the product, e.g. 'Rs. 500'."""
        return self.get_text(self.sel("product_price"))

    def is_added_modal_showing(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the add-to-cart confirmation modal is visible. WAITS."""
        return self.is_showing(self.sel("added_modal"), timeout_ms=timeout_ms)

    # ── actions ──────────────────────────────────────────────
    def set_quantity(self, quantity: int) -> None:
        """Set the desired quantity BEFORE adding to cart.

        Changing this after adding does not update the cart, so callers must
        set it first.
        """
        self.fill(self.sel("quantity_input"), str(quantity))

    def add_product_to_cart(self) -> None:
        """Click Add to cart and wait for the confirmation modal to appear."""
        self.click(self.sel("add_to_cart_button"))
        self.wait_visible(self.sel("added_modal"))

    def continue_shopping(self) -> None:
        """Dismiss the add-to-cart modal and stay on this product page.

        Required before any further interaction with the page underneath,
        because the modal blocks it. Waits for the modal to disappear so a
        following action does not land on the closing overlay.
        """
        self.click(self.sel("continue_shopping_button"))
        self.wait_hidden(self.sel("added_modal"))

    def open_cart_from_modal(self) -> None:
        """Click View Cart inside the add-to-cart modal to go to the cart.

        Prefer this over the nav Cart link right after adding a product: it
        also proves the modal appeared.
        """
        self.click(self.sel("view_cart_link_in_modal"))
