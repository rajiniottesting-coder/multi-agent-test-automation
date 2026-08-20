"""
ProductDetailPage — the single-product details screen (/product_details/{id}).

App: https://automationexercise.com

Selectors come from the `product_detail` page in the app inventory; this file
holds none as literals. Reach the page by clicking a product's View Product
link on the listing (the href already carries the id), then read the product
name and add it to the cart through the modal.
"""
from typing import Optional

from pages.base_page import BasePage


class ProductDetailPage(BasePage):
    """Product details. Selectors: see `product_detail` in the app inventory.

    Adding to cart opens a modal rather than navigating, so the two exits from
    that modal (View Cart / Continue Shopping) are exposed as explicit methods.
    """

    INVENTORY_PAGE = "product_detail"

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the product name is on screen. WAITS for it.

        The product name heading is present in every state this page can be in,
        so it is a stable readiness signal.
        """
        return self.is_showing(self.sel("product_name"), timeout_ms=timeout_ms)

    def product_name(self) -> str:
        """Return the product's name as shown on the detail page."""
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))

    def product_price(self) -> str:
        """Return the product's price text (rendered as 'Rs. 500')."""
        self.wait_visible(self.sel("product_price"))
        return self.get_text(self.sel("product_price"))

    def has_added_modal(self) -> bool:
        """True if the add-to-cart confirmation modal is showing. Never waits."""
        return self.is_visible(self.sel("added_modal"))

    # ── actions ──────────────────────────────────────────────
    def add_to_cart(self) -> None:
        """Click Add to cart for this product and wait for the modal to appear.

        The modal blocks the page underneath, so callers must exit it (via
        view_cart_from_modal or continue_shopping) before touching the page.
        """
        self.click(self.sel("add_to_cart_button"))
        self.wait_visible(self.sel("added_modal"))

    def view_cart_from_modal(self) -> None:
        """Follow the 'View Cart' link inside the add-to-cart modal.

        Navigates to the cart, so this proves the modal appeared as a side
        effect of the click.
        """
        self.wait_visible(self.sel("view_cart_link_in_modal"))
        self.click(self.sel("view_cart_link_in_modal"))

    def continue_shopping(self) -> None:
        """Dismiss the add-to-cart modal and stay on this product page."""
        self.wait_visible(self.sel("continue_shopping_button"))
        self.click(self.sel("continue_shopping_button"))
        self.wait_hidden(self.sel("added_modal"))
