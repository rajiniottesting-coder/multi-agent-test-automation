"""
ProductDetailPage — a single product's detail screen (/product_details/{id}).

New page object for the shopping-session feature. Conventions follow the
LoginPage reference:

  - SELECTORS COME FROM THE APP INVENTORY. Declare INVENTORY_PAGE, then use
    self.sel("<element_key>"). Never a literal selector string.
  - methods are business verbs that name WHAT they act on (open_product,
    add_to_cart), not bare verbs.
  - every method uses a BasePage helper; no raw self.page.* calls.
  - no assertions here — those belong in step definitions.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class ProductDetailPage(BasePage):
    """One product's detail page. Selectors: see `pages.product_detail`.

    The add-to-cart control here is UNIQUE (one per page), unlike the listing
    page's family of 68, so a cart scenario should add a product from here.
    """

    INVENTORY_PAGE = "product_detail"

    # ── actions ──────────────────────────────────────────────
    def open_product(self, base_url: str, product_id: int) -> None:
        """Navigate directly to a product's detail page by its id.

        Prefer reaching this page via a listing card's View Product link,
        whose href already carries the id; this direct form is for when the
        id is known independently.
        """
        self.navigate(f"{base_url.rstrip('/')}{self.page_url(product_id=product_id)}")

    def confirm_arrival(self, **params: object) -> None:
        """Confirm the browser reached a product detail page.

        The inventory URL is a template, so a plain URL match cannot be used.
        Instead wait for the product name element, which is unique to this page.
        """
        self.wait_visible(self.sel("product_name"))

    def set_quantity(self, quantity: int) -> None:
        """Set the desired quantity BEFORE adding to cart.

        Changing this after adding does not update the cart, so callers must
        set it first.
        """
        self.fill(self.sel("quantity_input"), str(quantity))

    def add_to_cart(self) -> None:
        """Click Add to cart, opening the confirmation modal on this page."""
        self.click(self.sel("add_to_cart_button"))

    def view_cart_from_modal(self) -> None:
        """From the add-to-cart modal, follow the View Cart link.

        Proves the modal appeared before navigating to the cart.
        """
        self.wait_visible(self.sel("added_modal"))
        self.click(self.sel("view_cart_link_in_modal"))

    def continue_shopping(self) -> None:
        """Dismiss the add-to-cart modal and stay on this product.

        Needed before any further interaction with the page underneath,
        because the modal blocks it.
        """
        self.wait_visible(self.sel("added_modal"))
        self.click(self.sel("continue_shopping_button"))

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the product detail page is on screen. WAITS for it.

        Probes the product name, which is present in every state this page
        can be in (the modal and review controls are conditional).
        """
        return self.is_showing(self.sel("product_name"), timeout_ms=timeout_ms)

    def product_name(self) -> str:
        """Visible product name (e.g. 'Blue Top'). WAITS for it."""
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))

    def product_price(self) -> str:
        """Visible product price, rendered as 'Rs. 500'. WAITS for it.

        Assert on the number, not the exact format.
        """
        self.wait_visible(self.sel("product_price"))
        return self.get_text(self.sel("product_price"))

    def is_add_to_cart_modal_shown(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the add-to-cart confirmation modal is visible. WAITS."""
        return self.is_showing(self.sel("added_modal"), timeout_ms=timeout_ms)
