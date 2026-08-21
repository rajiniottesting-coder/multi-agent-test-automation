"""
ProductDetailPage — a single product's detail screen (/product_details/{id}).

New page object for the cart-management feature. Reads the product's name and
price, adds it to the cart, dismisses or follows the add-to-cart modal, and
navigates to the cart.

Selectors come from `pages.product_detail` in the app inventory; this file
holds no literal selector strings — every element is resolved via
self.sel("<key>").

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage
from pages.cart_page import CartPage


class ProductDetailPage(BasePage):
    """A single product's detail page. Selectors: `pages.product_detail`.

    Reached by clicking a product's View Product link on the listing (that
    href already carries the id), or opened directly with the id template.
    Adding to cart opens a MODAL that blocks the page underneath, so a scenario
    adding the same product twice must dismiss it via continue_shopping()
    between clicks.
    """

    INVENTORY_PAGE = "product_detail"

    # ── actions ──────────────────────────────────────────────
    def open_product(self, base_url: str, product_id: int) -> None:
        """Navigate directly to a product's detail page by id."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url(product_id=product_id)}")

    def add_to_cart(self) -> None:
        """Click Add to cart and wait for the confirmation modal to appear.

        This product's add-to-cart control is unique on the page (unlike the
        listing's family of controls), so it is safe to click directly.
        """
        self.click(self.sel("add_to_cart_button"))
        self.wait_visible(self.sel("added_modal"))

    def continue_shopping(self) -> None:
        """Dismiss the add-to-cart modal and stay on this product page.

        Required before any further interaction with the page underneath — the
        modal blocks it, so a second Add to cart would otherwise land on the
        overlay.
        """
        self.click(self.sel("continue_shopping_button"))
        self.wait_hidden(self.sel("added_modal"))

    def view_cart_from_modal(self) -> None:
        """Follow the modal's View Cart link to the cart page.

        Ends by confirming the browser reached the cart, recovering from an ad
        interstitial that may have swallowed the navigation.
        """
        self.click(self.sel("view_cart_link_in_modal"))
        CartPage(self.page).confirm_arrival()

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the product name is on screen. WAITS for it."""
        return self.is_showing(self.sel("product_name"), timeout_ms=timeout_ms)

    def product_name(self) -> str:
        """The product's name as shown in the product information block."""
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))

    def product_price(self) -> str:
        """The product's price, e.g. 'Rs. 500'. Assert on the number."""
        self.wait_visible(self.sel("product_price"))
        return self.get_text(self.sel("product_price"))
