"""
ProductDetailPage — a single product's detail screen at /product_details/{product_id}.

Selectors: see `product_detail` in the app inventory. This page carries the
unique Add to cart control for ONE product (unlike the listing page's family
of buttons), which is why a cart scenario should add its product here.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class ProductDetailPage(BasePage):
    """Product detail page. Selectors: `product_detail` in the app inventory.

    Reached by clicking a product's View Product link on the listing — that
    href already carries the product id, so the test never invents one. The
    add-to-cart modal here appears only after Add to cart is clicked and blocks
    the page underneath until dismissed.
    """

    INVENTORY_PAGE = "product_detail"

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the product detail is on screen. WAITS for it.

        Probes the product name heading, which is present in every state of
        this page (the modal and review success are transient overlays).
        """
        return self.is_showing(self.sel("product_name"), timeout_ms=timeout_ms)

    def confirm_arrival(self, **params: object) -> None:
        """Confirm the browser reached this product detail page.

        Overrides BasePage.confirm_arrival to also wait for the product name,
        since the URL alone (a template with an embedded id) is not enough to
        know the content rendered.
        """
        self.wait_visible(self.sel("product_name"))

    def product_name(self) -> str:
        """Visible product name heading, e.g. 'Blue Top'. WAITS for it."""
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))

    def product_price(self) -> str:
        """Visible product price, rendered as 'Rs. 500'. WAITS for it.

        Assert on the number, not the exact format.
        """
        self.wait_visible(self.sel("product_price"))
        return self.get_text(self.sel("product_price"))

    # ── actions ──────────────────────────────────────────────
    def set_quantity(self, quantity: int) -> None:
        """Set the desired quantity BEFORE adding to cart.

        Changing the quantity after adding does not update the cart.
        """
        self.fill(self.sel("quantity_input"), str(quantity))

    def add_to_cart(self) -> None:
        """Click Add to cart and wait for the confirmation modal to appear.

        Adding opens a modal rather than navigating; it blocks the page
        underneath until dismissed or exited via View Cart.
        """
        self.click(self.sel("add_to_cart_button"))
        self.wait_visible(self.sel("added_modal"))

    def is_added_modal_shown(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the add-to-cart confirmation modal is visible. WAITS."""
        return self.is_showing(self.sel("added_modal"), timeout_ms=timeout_ms)

    def view_cart_from_modal(self) -> None:
        """Click View Cart inside the add-to-cart modal to enter the cart.

        Prefer this over the nav Cart link when a product was just added — it
        also proves the modal appeared.
        """
        self.wait_visible(self.sel("view_cart_link_in_modal"))
        self.click(self.sel("view_cart_link_in_modal"))

    def continue_shopping(self) -> None:
        """Dismiss the add-to-cart modal and stay on this product page.

        Required before any further interaction with the page underneath,
        because the modal blocks it.
        """
        self.wait_visible(self.sel("continue_shopping_button"))
        self.click(self.sel("continue_shopping_button"))
        self.wait_hidden(self.sel("added_modal"))
