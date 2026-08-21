"""
ProductDetailPage — a single product's detail screen (/product_details/{id}).

Selectors come from the app inventory under `product_detail`; this file never
contains a literal selector. Methods are business verbs that say WHAT they act
on, per the naming rule.

The add-to-cart control here is UNIQUE (unlike the listing page's family of
68), so cart scenarios add products from this page. Adding opens a MODAL that
blocks the page underneath — a scenario adding a product a second time on the
same page must dismiss it (Continue Shopping) between clicks, or the next
click lands on the overlay.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class ProductDetailPage(BasePage):
    """Product detail page. Selectors: see `product_detail` in the inventory."""

    INVENTORY_PAGE = "product_detail"

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the product detail page is on screen. WAITS for it.

        Probes the product name heading, which is present in every state of
        this page (the modal and review success are overlays on top of it).
        """
        return self.is_showing(self.sel("product_name"), timeout_ms=timeout_ms)

    def product_name(self) -> str:
        """The product's name as rendered in the product information block."""
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))

    def product_price(self) -> str:
        """The product's price, rendered as e.g. 'Rs. 500'."""
        self.wait_visible(self.sel("product_price"))
        return self.get_text(self.sel("product_price"))

    def is_added_modal_shown(self) -> bool:
        """True once the add-to-cart confirmation modal is visible. WAITS."""
        return self.is_showing(self.sel("added_modal"))

    # ── actions ──────────────────────────────────────────────
    def set_quantity(self, quantity: int) -> None:
        """Set the desired quantity BEFORE adding to cart.

        Changing this after adding does not update the cart, so callers must
        set it first.
        """
        self.fill(self.sel("quantity_input"), str(quantity))

    def add_to_cart(self) -> None:
        """Click Add to cart and wait for the confirmation modal to appear."""
        self.click(self.sel("add_to_cart_button"))
        self.wait_visible(self.sel("added_modal"))

    def view_cart_from_modal(self) -> None:
        """From the add-to-cart modal, follow View Cart to the cart page."""
        self.click(self.sel("view_cart_link_in_modal"))

    def continue_shopping_from_modal(self) -> None:
        """Dismiss the add-to-cart modal and stay on this product page.

        Required before any further interaction with the page underneath,
        because the modal blocks it. Waits for the modal to disappear so a
        subsequent Add to cart does not land on the overlay.
        """
        self.click(self.sel("continue_shopping_button"))
        self.wait_hidden(self.sel("added_modal"))
