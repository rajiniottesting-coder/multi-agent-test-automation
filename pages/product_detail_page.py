"""
ProductDetailPage — a single product's detail screen (/product_details/{id}).

Style copied from pages/login_page.py:
  - selectors come from the app inventory via self.sel("<key>"), never literals
  - INVENTORY_PAGE names the inventory page key
  - methods are business verbs that say WHAT they act on (open_product,
    add_product_to_cart), never bare verbs
  - every method uses a BasePage helper; no raw self.page.* calls
  - no assertions here — those belong in step definitions

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class ProductDetailPage(BasePage):
    """Product detail page. Selectors: see `pages.product_detail` in the inventory.

    One page per product, addressed by a URL template carrying the product id.
    Reach it by clicking a product's View Product link on the listing so the
    href supplies the id — but open_product() is provided for direct navigation.
    """

    INVENTORY_PAGE = "product_detail"

    # ── actions ──────────────────────────────────────────────
    def open_product(self, base_url: str, product_id: int) -> None:
        """Navigate directly to a product's detail page by id.

        Prefer reaching this page via the listing's View Product link, which
        already carries the correct id; this method exists for direct linking.
        """
        path = self.page_url(product_id=product_id)
        self.navigate(f"{base_url.rstrip('/')}{path}")
        self.confirm_arrival(product_id=product_id)

    def add_product_to_cart(self) -> None:
        """Click Add to cart, opening the confirmation modal on this page.

        The modal blocks the page underneath, so any further interaction with
        this page must first dismiss it via continue_shopping().
        """
        self.click(self.sel("add_to_cart_button"))
        self.wait_visible(self.sel("added_modal"))

    def view_cart_from_modal(self) -> None:
        """From the add-to-cart modal, follow the View Cart link to the cart."""
        self.wait_visible(self.sel("added_modal"))
        self.click(self.sel("view_cart_link_in_modal"))

    def continue_shopping(self) -> None:
        """Dismiss the add-to-cart modal and stay on this product page."""
        self.click(self.sel("continue_shopping_button"))
        self.wait_hidden(self.sel("added_modal"))

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the product name is on screen. WAITS for it.

        The product name is present in every state of this page, so it is a
        stable readiness signal (the modal and review-success elements are
        conditional and cannot serve).
        """
        return self.is_showing(self.sel("product_name"), timeout_ms=timeout_ms)

    def product_name(self) -> str:
        """The product's name. WAITS for it to appear."""
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))

    def product_price(self) -> str:
        """The product's price text, rendered as 'Rs. 500'. WAITS for it.

        Assert on the number within, not the exact format.
        """
        self.wait_visible(self.sel("product_price"))
        return self.get_text(self.sel("product_price"))

    def is_added_modal_visible(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the add-to-cart confirmation modal is showing. WAITS."""
        return self.is_showing(self.sel("added_modal"), timeout_ms=timeout_ms)
