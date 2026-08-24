"""
ProductDetailPage — a single product's detail page (/product_details/{id}).

New page object for the shopping-session feature. Conventions mirror
LoginPage: selectors come from the app inventory via self.sel(...), methods
are business verbs that name what they act on, and every method uses a
BasePage helper rather than raw self.page.* calls. No assertions here.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class ProductDetailPage(BasePage):
    """A single product's detail page. Selectors: see `product_detail` in the
    app inventory.

    Reached by clicking a product's View Product link on the listing, which
    carries the product id in its href — so the test never invents an id.
    """

    INVENTORY_PAGE = "product_detail"

    # ── actions ──────────────────────────────────────────────
    def add_to_cart(self) -> None:
        """Click the single Add to cart control for THIS product.

        Adding opens a modal rather than navigating; the modal blocks the page
        underneath, so dismiss it (or leave via View Cart) before any further
        interaction with the page.
        """
        self.click(self.sel("add_to_cart_button"))
        self.wait_visible(self.sel("added_modal"))

    def dismiss_added_modal(self) -> None:
        """Close the add-to-cart modal via Continue Shopping and stay here.

        Needed before any further interaction with the page underneath — the
        modal blocks it while open.
        """
        self.click(self.sel("continue_shopping_button"))
        self.wait_hidden(self.sel("added_modal"))

    def view_cart_from_modal(self) -> None:
        """Follow View Cart inside the add-to-cart modal, landing on the cart.

        This proves the modal appeared and navigates to the cart in one step.
        """
        self.click(self.sel("view_cart_link_in_modal"))

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the product name is on screen. WAITS for it.

        The product name is the most state-independent element on this page —
        it is present in every state, unlike the add-to-cart modal or the
        review-success message, which appear only after an interaction.
        """
        return self.is_showing(self.sel("product_name"), timeout_ms=timeout_ms)

    def product_name(self) -> str:
        """The product's displayed name. WAITS for it to appear."""
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))
