"""
MenuPage — the sidebar and top bar present on every authenticated page.

EXTENDABLE: Agent 2 may add methods here as new stories need them. Follow the
conventions in pages/login_page.py — selectors from the app inventory via
self.sel(), business verbs, BasePage helpers only.

Implements the four methods the inventory declares under `key_methods`:
go_to(module), open_user_menu(), logout(), get_toast_text().
"""
from pages.base_page import BasePage


class MenuPage(BasePage):
    """Navigation chrome. Selectors: `pages.menu` in the inventory.

    The inventory marks this page `always: true`, so it is injected into every
    generation prompt — any authenticated scenario may need to navigate.
    """

    INVENTORY_PAGE = "menu"

    # Visible module names, in sidebar order. Each maps to an inventory key by
    # the convention "<lowercased, spaces as underscores>_link", so no selector
    # is written here — go_to() derives the key and self.sel() resolves it.
    MODULES = (
        "Admin", "PIM", "Leave", "Time", "Recruitment", "My Info",
        "Performance", "Dashboard", "Directory", "Maintenance",
        "Claim", "Buzz",
    )

    # ── navigation ───────────────────────────────────────────
    def go_to(self, module: str) -> None:
        """Click a sidebar module by its visible name, e.g. "Admin", "My Info".

        Case- and separator-insensitive: "my info", "My-Info" and "MY INFO" all
        resolve. Raises ValueError naming every valid module if the name is
        unknown, so a typo in a feature file fails with an actionable message
        rather than a selector timeout.
        """
        key = self._module_key(module)
        self.click(self.sel(key))

    def is_module_visible(self, module: str) -> bool:
        """True if a module link is on screen. Never raises, never waits."""
        return self.is_visible(self.sel(self._module_key(module)))

    def search_menu(self, term: str) -> None:
        """Type into the sidebar's module search box."""
        self.type(self.sel("menu_search_input"), term)

    def toggle_sidebar(self) -> None:
        """Collapse or expand the sidebar."""
        self.click(self.sel("sidebar_toggle"))

    # ── user menu ────────────────────────────────────────────
    def open_user_menu(self) -> None:
        """Open the top-right user dropdown.

        logout_link only renders after this is clicked — the crawler could not
        see it, per the inventory note — so logout() calls this first.
        """
        self.click(self.sel("user_dropdown"))

    def logout(self) -> None:
        """Open the user dropdown and click Logout."""
        self.open_user_menu()
        self.wait_visible(self.sel("logout_link"))
        self.click(self.sel("logout_link"))

    # ── queries ──────────────────────────────────────────────
    def get_toast_text(self) -> str:
        """Text of the success/error toast, e.g. 'Successfully Saved'.

        Waits for the toast to appear, so only call this when one is expected.
        Use has_toast() to check whether any toast is present.
        """
        self.wait_visible(self.sel("toast"))
        return self.get_text(self.sel("toast"))

    def has_toast(self) -> bool:
        """True if a toast is currently showing. Never raises.

        The non-waiting counterpart to get_toast_text(). The toast element is
        in the DOM but empty until an action fires, so this checks for text
        rather than mere presence.
        """
        return bool(self.get_all_texts(self.sel("toast")))

    # ── internals ────────────────────────────────────────────
    def _module_key(self, module: str) -> str:
        """Map a visible module name to its inventory element key."""
        normalised = module.strip().lower().replace("-", "_").replace(" ", "_")
        key = f"{normalised}_link"
        valid = {m.strip().lower().replace(" ", "_"): m for m in self.MODULES}
        if normalised not in valid:
            raise ValueError(
                f"Unknown menu module {module!r}. Valid modules are: "
                f"{', '.join(self.MODULES)}."
            )
        return key