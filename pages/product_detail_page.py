"""
ProductDetailPage — a single product's detail screen (/product_details/{id}).

Selectors: see `product_detail` in the app inventory. This page carries one
add-to-cart control (unique, unlike the listing page's family), a quantity
input, and an add-to-cart MODAL that appears only after adding. The modal
blocks the page underneath, so a scenario adding a second product from the
same page must dismiss it (continue shopping) before clicking again.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class ProductDetailPage(BasePage):
    """Product detail page. Selectors: see `product_detail` in the inventory."""

    INVENTORY_PAGE = "product_detail"

    # ── navigation ───────────────────────────────────────────
    def open_product(self, base_url: str, product_id: int) -> None:
        """Navigate directly to a product's detail page by its id.

        Prefer reaching this page by clicking a product's View Product link on
        the listing, whose href already carries the id — this method is for
        when only the id is known.
        """
        path = self.page_url(product_id=product_id)
        self.navigate(f"{base_url.rstrip('/')}{path}")

    # ── actions ──────────────────────────────────────────────
    def set_quantity(self, quantity: int) -> None:
        """Set the quantity BEFORE adding to cart; changing it afterwards does
        not update the cart."""
        self.fill(self.sel("quantity_input"), str(quantity))

    def add_to_cart(self) -> None:
        """Click this product's single Add to cart control. Opens the modal."""
        self.click(self.sel("add_to_cart_button"))

    def go_to_cart_from_modal(self) -> None:
        """Click View Cart inside the add-to-cart modal.

        Waits for the modal first, which also proves the add succeeded.
        Navigates to the cart, so confirm arrival there is the caller's job.
        """
        self.wait_visible(self.sel("added_modal"))
        self.click(self.sel("view_cart_link_in_modal"))

    def continue_shopping(self) -> None:
        """Dismiss the add-to-cart modal and stay on this product page.

        Required before any further interaction with the page underneath — the
        modal blocks it. Waits for the modal, then for it to close.
        """
        self.wait_visible(self.sel("added_modal"))
        self.click(self.sel("continue_shopping_button"))
        self.wait_hidden(self.sel("added_modal"))

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the product name is on screen. WAITS for it."""
        return self.is_showing(self.sel("product_name"), timeout_ms=timeout_ms)

    def product_name(self) -> str:
        """The product's name. WAITS for it to appear."""
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))

    def product_price(self) -> str:
        """The product's price text (rendered as 'Rs. 500'). WAITS for it.

        Assert on the number, not the format.
        """
        self.wait_visible(self.sel("product_price"))
        return self.get_text(self.sel("product_price"))

    def is_added_modal_showing(self) -> bool:
        """True once the add-to-cart modal is visible. WAITS for it.

        Call this only where the modal is EXPECTED (right after adding). To
        branch on the modal's presence, use is_visible on the selector instead.
        """
        return self.is_showing(self.sel("added_modal"))
