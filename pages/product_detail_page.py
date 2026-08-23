"""
ProductDetailPage — a single product's detail screen (/product_details/{id}).

Selectors: see `pages.product_detail` in the app inventory. Set INVENTORY_PAGE
and resolve every element via self.sel("<key>"); never a literal selector here.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class ProductDetailPage(BasePage):
    """A single product's detail page.

    Reached by clicking a product's View Product link on the listing (the href
    already carries the id), or opened directly by id. The Add to cart control
    here is unique to this product — unlike the listing's family of controls —
    which is why cart scenarios add from here.
    """

    INVENTORY_PAGE = "product_detail"

    # ── navigation ───────────────────────────────────────────
    def open_product(self, base_url: str, product_id: int) -> None:
        """Open this product's detail page directly by id.

        Prefer reaching the page via the listing's View Product link where a
        scenario already has a product name — that link carries the real id so
        the test never invents one. This is the by-id fallback.
        """
        self.navigate(f"{base_url.rstrip('/')}{self.page_url(product_id=product_id)}")
        self.confirm_arrival(product_id=product_id)

    # ── actions ──────────────────────────────────────────────
    def add_to_cart(self) -> None:
        """Add this product to the cart, opening the 'Added!' modal.

        Adding does not navigate — it opens a modal that blocks the page
        underneath, so dismiss it (continue_shopping) or use it to navigate
        (open_cart_from_modal) before interacting with the page again.
        """
        self.click(self.sel("add_to_cart_button"))
        self.wait_visible(self.sel("added_modal"))

    def continue_shopping(self) -> None:
        """Dismiss the add-to-cart modal and stay on this product page.

        Needed before any further interaction with the page underneath,
        because the modal blocks it.
        """
        self.click(self.sel("continue_shopping_button"))
        self.wait_hidden(self.sel("added_modal"))

    def open_cart_from_modal(self) -> None:
        """Navigate to the cart via the modal's View Cart link.

        Preferred over the nav Cart link right after adding a product, because
        it also proves the modal appeared.
        """
        self.click(self.sel("view_cart_link_in_modal"))

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self) -> bool:
        """True once the product detail page has rendered. WAITS for it.

        Probes the product name heading, which is present in every state this
        page can be in — the modal and review-success elements are conditional
        and absent on a fresh load.
        """
        return self.is_showing(self.sel("product_name"))

    def product_name(self) -> str:
        """Visible name of the product on this detail page. WAITS for it."""
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))

    def product_price(self) -> str:
        """Visible price of the product, e.g. 'Rs. 500'. WAITS for it.

        Rendered with a currency prefix; assert on the number, not the format.
        """
        self.wait_visible(self.sel("product_price"))
        return self.get_text(self.sel("product_price"))

    def modal_is_showing(self) -> bool:
        """True once the add-to-cart modal is visible. WAITS for it.

        Call this only where the modal is the expected state — it times out if
        the modal never appears.
        """
        return self.is_showing(self.sel("added_modal"))
