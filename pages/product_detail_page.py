"""
ProductDetailPage — a single product's detail screen (/product_details/{id}).

Selectors come from the `product_detail` page in the app inventory; this file
declares INVENTORY_PAGE and looks every element up with self.sel("<key>").

The page is normally reached by clicking a product's View Product link on the
listing, which carries the product id in its href — so the test never has to
invent one. open_product() supports the template form when a scenario needs it.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class ProductDetailPage(BasePage):
    """One product's detail page. Selectors: see `product_detail` in the inventory.

    The add-to-cart control here is UNIQUE (unlike the listing's family of 68),
    which is why a cart scenario should add a product from this page.
    """

    INVENTORY_PAGE = "product_detail"

    # ── actions ──────────────────────────────────────────────
    def open_product(self, base_url: str, product_id: int) -> None:
        """Navigate directly to a product's detail page by id."""
        path = self.page_url(product_id=product_id)
        self.navigate(f"{base_url.rstrip('/')}{path}")

    def add_product_to_cart(self) -> None:
        """Click Add to cart for this product, opening the confirmation modal."""
        self.click(self.sel("add_to_cart_button"))

    def open_cart_from_modal(self) -> None:
        """From the add-to-cart modal, follow View Cart to the cart page."""
        self.wait_visible(self.sel("added_modal"))
        self.click(self.sel("view_cart_link_in_modal"))

    def continue_shopping(self) -> None:
        """Dismiss the add-to-cart modal and stay on this product page."""
        self.wait_visible(self.sel("added_modal"))
        self.click(self.sel("continue_shopping_button"))

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the product name is on screen. WAITS for it."""
        return self.is_showing(self.sel("product_name"), timeout_ms=timeout_ms)

    def product_name(self) -> str:
        """The product's name as shown in the product information block."""
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))

    def product_price(self) -> str:
        """The product's price, rendered like 'Rs. 500'."""
        self.wait_visible(self.sel("product_price"))
        return self.get_text(self.sel("product_price"))

    def is_add_confirmation_shown(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the 'added to cart' modal is visible. WAITS for it."""
        return self.is_showing(self.sel("added_modal"), timeout_ms=timeout_ms)
