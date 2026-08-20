"""
ProductDetailPage — a single product's detail screen at /product_details/{product_id}.

New page object for the cart-management feature. Selectors come from the
`product_detail` page in the app inventory; this file never contains a literal
selector string. Method names say WHAT they act on (add_product_to_cart,
continue_shopping) rather than bare verbs.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class ProductDetailPage(BasePage):
    """One product's detail page. Selectors: see `product_detail` in the app inventory.

    Reached by clicking a product's View Product link on the listing — that href
    already carries the product id — or by open_product(product_id). Adding to
    cart opens a modal that blocks the page underneath, so a scenario adding a
    second product must dismiss it first via continue_shopping().
    """

    INVENTORY_PAGE = "product_detail"

    # ── actions ──────────────────────────────────────────────
    def open_product(self, base_url: str, product_id: int) -> None:
        """Navigate directly to a product's detail page by its id."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url(product_id=product_id)}")

    def add_product_to_cart(self) -> None:
        """Click Add to cart, opening the confirmation modal for this product."""
        self.click(self.sel("add_to_cart_button"))
        self.wait_visible(self.sel("added_modal"))

    def continue_shopping(self) -> None:
        """Dismiss the add-to-cart modal and stay on this product page.

        Required before any further interaction with the page underneath,
        because the modal blocks it.
        """
        self.click(self.sel("continue_shopping_button"))
        self.wait_hidden(self.sel("added_modal"))

    def view_cart(self) -> None:
        """Follow the modal's View Cart link, navigating to the cart page."""
        self.click(self.sel("view_cart_link_in_modal"))

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the product name is on screen. WAITS for it.

        product_name is the most state-independent element here: it is present
        regardless of whether the add-to-cart modal or a review form is open.
        """
        return self.is_showing(self.sel("product_name"), timeout_ms=timeout_ms)

    def product_name(self) -> str:
        """The product's title text."""
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))

    def is_added_modal_showing(self) -> bool:
        """True if the add-to-cart confirmation modal is visible. WAITS for it."""
        return self.is_showing(self.sel("added_modal"))
