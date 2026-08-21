"""
ProductDetailPage — a single product's detail screen (/product_details/{id}).

New page object for the shopping-session feature. Reached by clicking a
product's View Product link on the listing (that href already carries the id),
or by URL for a known product id. From here a shopper adds the product to the
cart and moves on to the cart via the add-to-cart modal.

Conventions (see pages/login_page.py for the worked reference):
  - selectors come from the app inventory via self.sel("<key>"), never literals
  - methods are business verbs that name their subject (open_product_by_id,
    add_to_cart, go_to_cart_from_modal), not bare verbs
  - every method uses a BasePage helper; no raw self.page.* calls
  - no assertions here — those belong in step definitions

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class ProductDetailPage(BasePage):
    """Product detail screen. Selectors: see `pages.product_detail` in inventory.

    The URL is a TEMPLATE — one page per product — so open_product_by_id()
    fills the id into the inventory path rather than inventing an address.
    Prefer reaching this page by clicking a listing card's View Product link,
    which already carries the id.
    """

    INVENTORY_PAGE = "product_detail"

    # ── actions ──────────────────────────────────────────────
    def open_product_by_id(self, base_url: str, product_id: str) -> None:
        """Navigate directly to a product's detail page by its id."""
        path = self.page_url(product_id=product_id)
        self.navigate(f"{base_url.rstrip('/')}{path}")

    def set_quantity(self, quantity: str) -> None:
        """Set the desired quantity BEFORE adding to cart.

        Changing the quantity after adding does not update the cart, so this
        must run before add_to_cart().
        """
        self.fill(self.sel("quantity_input"), quantity)

    def add_to_cart(self) -> None:
        """Click the single Add to cart control for this product.

        Opens a modal rather than navigating; the modal blocks the page
        underneath until dismissed or followed to the cart.
        """
        self.click(self.sel("add_to_cart_button"))
        self.wait_visible(self.sel("added_modal"))

    def go_to_cart_from_modal(self) -> None:
        """Follow the View Cart link inside the add-to-cart modal.

        Navigates to /view_cart. Proves the modal appeared, since the link
        only exists once the product was added.
        """
        self.click(self.sel("view_cart_link_in_modal"))

    def continue_shopping(self) -> None:
        """Dismiss the add-to-cart modal and stay on this product page.

        Needed before any further interaction with the page underneath,
        because the modal blocks it.
        """
        self.click(self.sel("continue_shopping_button"))
        self.wait_hidden(self.sel("added_modal"))

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the product name is on screen. WAITS for it.

        The product name is the most state-independent element here: price,
        availability and the review controls are all present too, but the name
        is the clearest signal that a specific product's detail page rendered.
        """
        return self.is_showing(self.sel("product_name"), timeout_ms=timeout_ms)

    def product_name(self) -> str:
        """The product's name as shown on the detail page. WAITS for it."""
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))

    def product_price(self) -> str:
        """The product's price text, e.g. 'Rs. 500'. WAITS for it.

        Rendered with the 'Rs. ' prefix; a step asserting a price should match
        on containment rather than equality.
        """
        self.wait_visible(self.sel("product_price"))
        return self.get_text(self.sel("product_price"))

    def has_added_modal(self) -> bool:
        """True if the add-to-cart modal is showing right now. Never waits.

        Non-waiting probe for branching or absence checks. Use add_to_cart()'s
        built-in wait to assert the modal DID appear.
        """
        return self.is_visible(self.sel("added_modal"))
