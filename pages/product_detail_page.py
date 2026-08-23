"""
ProductDetailPage — a single product's detail screen (/product_details/{id}).

Reads the product name and price, adds the product to the cart, and provides
the two ways out of the add-to-cart modal (View Cart, Continue Shopping).

Selectors: see `pages.product_detail` in the app inventory. This file holds no
literal selectors — every element is looked up by its inventory KEY.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage
from pages.cart_page import CartPage


class ProductDetailPage(BasePage):
    """One product's detail page. Selectors: `pages.product_detail` inventory.

    The URL is a template (/product_details/{product_id}), so reach this page
    by clicking a product's View Product link on the listing — that href
    already carries the id — or open it directly with a known product_id.
    """

    INVENTORY_PAGE = "product_detail"

    # ── navigation ───────────────────────────────────────────
    def open_product(self, base_url: str, product_id: int) -> None:
        """Navigate directly to a specific product's detail page by id."""
        path = self.page_url(product_id=product_id)
        self.navigate(f"{base_url.rstrip('/')}{path}")
        self.confirm_arrival(product_id=product_id)

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the product name is on screen. WAITS for it.

        The product name is the most state-independent element on this page —
        it is present on every product's detail view regardless of whether the
        add-to-cart modal or a review has been triggered.
        """
        return self.is_showing(self.sel("product_name"), timeout_ms=timeout_ms)

    def product_name(self) -> str:
        """The product's name. WAITS for it to appear."""
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))

    def product_price(self) -> str:
        """The product's price, rendered as 'Rs. 500'. WAITS for it.

        Assert on the number within, not the exact format.
        """
        self.wait_visible(self.sel("product_price"))
        return self.get_text(self.sel("product_price"))

    # ── actions ──────────────────────────────────────────────
    def add_to_cart(self) -> None:
        """Click Add to cart for THIS product, opening the confirmation modal."""
        self.click(self.sel("add_to_cart_button"))
        self.wait_visible(self.sel("added_modal"))

    def is_added_modal_showing(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the add-to-cart confirmation modal is visible. WAITS.

        Call this only where the modal is expected — it is asserted on after
        a successful add to cart.
        """
        return self.is_showing(self.sel("added_modal"), timeout_ms=timeout_ms)

    def go_to_cart_from_modal(self) -> CartPage:
        """Click View Cart inside the add-to-cart modal, landing on the cart.

        Returns a CartPage so the caller can read the cart it just reached.
        """
        self.click(self.sel("view_cart_link_in_modal"))
        cart = CartPage(self.page)
        cart.confirm_arrival()
        return cart

    def continue_shopping(self) -> None:
        """Dismiss the add-to-cart modal and stay on this product page.

        Needed before any further interaction with the page underneath — the
        modal blocks it.
        """
        self.click(self.sel("continue_shopping_button"))
        self.wait_hidden(self.sel("added_modal"))
