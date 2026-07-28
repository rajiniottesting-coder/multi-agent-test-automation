"""
BasePage — parent class for all page objects.
Holds the Playwright `page` reference and common actions.

This base class covers every control type a web application exposes: text
inputs, checkboxes, radios, native and custom dropdowns, hover menus,
drag-and-drop, file uploads, iframes, tables/lists, dialogs, new tabs and
downloads.

The intent is that page objects rarely touch `self.page` directly — they
compose these helpers instead. That keeps Playwright specifics in ONE file
and makes generated page objects consistent.

All methods here are app-agnostic — they accept locator strings and operate
on whatever element they are pointed at.

SELECTORS LIVE IN THE APP INVENTORY, NOT IN PAGE OBJECTS
--------------------------------------------------------
A page object declares which inventory page it implements and looks selectors
up by KEY:

    class SomePage(BasePage):
        INVENTORY_PAGE = "<page key from the inventory>"

        def do_something(self, value):
            self.fill(self.sel("<element key on that page>"), value)

`app_inventory/<app>.json` is the single source of truth. Two reasons:

1. Agent 2 CANNOT hallucinate a selector it never writes. Emitting
   `self.sel("<key>")` is checkable against the inventory; emitting a literal
   selector string is not.
2. A selector fixed in the inventory takes effect everywhere at once, with no
   second edit and no chance of the two copies disagreeing.

An unknown key raises immediately, naming the page and listing what IS
available — a failure at the first use, not a silent mis-selection later.

Locator strings may be any Playwright selector: CSS, `text=`, `role=`, or an
iframe-chained selector using ' >>> '. Open shadow DOM is pierced by CSS
automatically.
"""
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlparse

from playwright.sync_api import Locator, Page, expect


class BasePage:
    """Every page object inherits from this."""

    # Default timeout for "wait and assert" helpers — short enough to fail
    # fast on broken pages, long enough to absorb normal network jitter.
    DEFAULT_TIMEOUT_MS = 5000

    # Subclasses set this to the key of the page they implement in
    # app_inventory/<app>.json. Left None only by BasePage itself.
    INVENTORY_PAGE: Optional[str] = None

    # Parsed inventory, shared by every page object in the process.
    _INVENTORY_CACHE: Optional[Dict[str, Any]] = None

    def __init__(self, page: Page):
        self.page = page

    # ============================================================
    # Selectors — resolved from the app inventory
    # ============================================================

    @classmethod
    def _inventory(cls) -> Dict[str, Any]:
        """The parsed app inventory, loaded once per process."""
        if BasePage._INVENTORY_CACHE is None:
            import json
            import yaml
            from config.paths import CONFIG_YAML, PROJECT_ROOT
            cfg = yaml.safe_load(CONFIG_YAML.read_text(encoding="utf-8")) or {}
            rel = (cfg.get("app_under_test") or {}).get("inventory_file")
            if not rel:
                raise RuntimeError(
                    "config.yaml has no app_under_test.inventory_file — page "
                    "objects cannot resolve selectors without it."
                )
            path = PROJECT_ROOT / rel
            if not path.is_file():
                raise FileNotFoundError(
                    f"App inventory not found at {path}. Page objects read "
                    f"their selectors from it; generate one with "
                    f"`python -m scripts.generate_inventory`."
                )
            BasePage._INVENTORY_CACHE = json.loads(path.read_text(encoding="utf-8"))
        return BasePage._INVENTORY_CACHE

    @classmethod
    def sel(cls, key: str) -> str:
        """Selector for `key` on this page object's inventory page.

        Raises with the available keys rather than returning None, so a typo
        fails at first use instead of quietly matching nothing.
        """
        if not cls.INVENTORY_PAGE:
            raise RuntimeError(
                f"{cls.__name__} has no INVENTORY_PAGE set. Point it at the key "
                f"of the page it implements in the app inventory."
            )
        pages = cls._inventory().get("pages") or {}
        page = pages.get(cls.INVENTORY_PAGE)
        if page is None:
            raise KeyError(
                f"{cls.__name__}.INVENTORY_PAGE = {cls.INVENTORY_PAGE!r} is not "
                f"in the app inventory. Available pages: "
                f"{', '.join(sorted(pages))}"
            )
        elements = page.get("elements") or {}
        if key not in elements:
            raise KeyError(
                f"{cls.__name__}: no element {key!r} on inventory page "
                f"{cls.INVENTORY_PAGE!r}. Available: "
                f"{', '.join(sorted(elements))}"
            )
        return elements[key]

    @classmethod
    def page_url(cls) -> str:
        """URL path for this page object's inventory page."""
        if not cls.INVENTORY_PAGE:
            raise RuntimeError(f"{cls.__name__} has no INVENTORY_PAGE set.")
        pages = cls._inventory().get("pages") or {}
        return (pages.get(cls.INVENTORY_PAGE) or {}).get("url", "/")

    # ============================================================
    # Internal
    # ============================================================

    def _locator(self, locator: str) -> Locator:
        """Resolve a selector, entering iframes when it uses the ' >>> ' chain.

        'iframe#pay >>> [data-test=card]' becomes
        page.frame_locator('iframe#pay').locator('[data-test=card]').
        """
        if ">>>" not in locator:
            return self.page.locator(locator)
        parts = [p.strip() for p in locator.split(">>>")]
        element = parts[-1]
        scope: Any = self.page
        for frame_selector in parts[:-1]:
            scope = scope.frame_locator(frame_selector)
        return scope.locator(element)

    def _timeout(self, timeout_ms: Optional[int]) -> int:
        return timeout_ms if timeout_ms is not None else self.DEFAULT_TIMEOUT_MS

    # ============================================================
    # Navigation and page state
    # ============================================================

    def navigate(self, url: str) -> None:
        """Go to an absolute URL."""
        self.page.goto(url)

    def reload(self) -> None:
        """Reload the current page."""
        self.page.reload()

    def go_back(self) -> None:
        """Browser back."""
        self.page.go_back()

    def go_forward(self) -> None:
        """Browser forward."""
        self.page.go_forward()

    def get_title(self) -> str:
        """Document title."""
        return self.page.title()

    def get_url(self) -> str:
        """Current URL."""
        return self.page.url

    def get_path(self) -> str:
        """Path portion of the current URL, without host or query."""
        return urlparse(self.page.url).path

    def url_matches(self, expected_url: str) -> bool:
        """Compare URLs ignoring a trailing slash on either side."""
        return self.page.url.rstrip("/") == expected_url.rstrip("/")

    def wait_for_url(self, url_pattern: str,
                     timeout_ms: Optional[int] = None) -> None:
        """Wait until the URL matches a glob or regex pattern."""
        self.page.wait_for_url(url_pattern, timeout=self._timeout(timeout_ms))

    def wait_for_page_load(self, state: str = "networkidle",
                           timeout_ms: Optional[int] = None) -> None:
        """Wait for a load state: 'load', 'domcontentloaded' or 'networkidle'."""
        self.page.wait_for_load_state(state, timeout=self._timeout(timeout_ms))

    # ============================================================
    # Waiting and element state
    # ============================================================

    def wait_visible(self, locator: str,
                     timeout_ms: Optional[int] = None) -> None:
        """Wait until the element is visible; raises if it never appears."""
        expect(self._locator(locator)).to_be_visible(
            timeout=self._timeout(timeout_ms))

    def wait_hidden(self, locator: str,
                    timeout_ms: Optional[int] = None) -> None:
        """Wait until the element is hidden or detached."""
        expect(self._locator(locator)).to_be_hidden(
            timeout=self._timeout(timeout_ms))

    def wait_enabled(self, locator: str,
                     timeout_ms: Optional[int] = None) -> None:
        """Wait until the element is enabled."""
        expect(self._locator(locator)).to_be_enabled(
            timeout=self._timeout(timeout_ms))

    def wait_for_text(self, locator: str, text: str,
                      timeout_ms: Optional[int] = None) -> None:
        """Wait until the element contains the given text."""
        expect(self._locator(locator)).to_contain_text(
            text, timeout=self._timeout(timeout_ms))

    def is_visible(self, locator: str) -> bool:
        """True if the element is currently visible (no waiting)."""
        return self._locator(locator).is_visible()

    def is_enabled(self, locator: str) -> bool:
        """True if the element is enabled."""
        return self._locator(locator).is_enabled()

    def is_editable(self, locator: str) -> bool:
        """True if the element accepts input."""
        return self._locator(locator).is_editable()

    def exists(self, locator: str) -> bool:
        """True if at least one element matches."""
        return self._locator(locator).count() > 0

    # ============================================================
    # Text and attributes
    # ============================================================

    def get_text(self, locator: str) -> str:
        """Visible text of the first match, stripped."""
        return (self._locator(locator).inner_text() or "").strip()

    def get_all_texts(self, locator: str) -> List[str]:
        """Visible text of every match, stripped, in DOM order."""
        return [t.strip() for t in self._locator(locator).all_inner_texts()]

    def get_attribute(self, locator: str, name: str) -> Optional[str]:
        """Value of an HTML attribute, or None if absent."""
        return self._locator(locator).get_attribute(name)

    def get_count(self, locator: str) -> int:
        """Number of elements matching the locator."""
        return self._locator(locator).count()

    # ============================================================
    # Text inputs
    # ============================================================

    def fill(self, locator: str, value: str) -> None:
        """Clear the field and set its value in one action."""
        self._locator(locator).fill(value)

    def type_text(self, locator: str, value: str, delay_ms: int = 50) -> None:
        """Type character by character — for fields with keystroke handlers."""
        self._locator(locator).press_sequentially(value, delay=delay_ms)

    def clear(self, locator: str) -> None:
        """Empty an input."""
        self._locator(locator).fill("")

    def get_input_value(self, locator: str) -> str:
        """Current value of an input/textarea (DOM property, not text)."""
        return self._locator(locator).input_value()

    def get_placeholder(self, locator: str) -> Optional[str]:
        """Placeholder text of an input."""
        return self._locator(locator).get_attribute("placeholder")

    def press_key(self, locator: str, key: str) -> None:
        """Press a key with the element focused, e.g. 'Enter', 'Tab'."""
        self._locator(locator).press(key)

    # ============================================================
    # Clicking
    # ============================================================

    def click(self, locator: str) -> None:
        """Click the element."""
        self._locator(locator).click()

    def double_click(self, locator: str) -> None:
        """Double-click the element."""
        self._locator(locator).dblclick()

    def right_click(self, locator: str) -> None:
        """Right-click (context menu) the element."""
        self._locator(locator).click(button="right")

    def click_if_visible(self, locator: str) -> bool:
        """Click only if present; returns whether it clicked.

        For optional UI such as cookie banners that may not appear.
        """
        target = self._locator(locator)
        if target.count() > 0 and target.is_visible():
            target.click()
            return True
        return False

    def force_click(self, locator: str) -> None:
        """Click bypassing actionability checks — last resort for overlays."""
        self._locator(locator).click(force=True)

    # ============================================================
    # Checkboxes and radio buttons
    # ============================================================

    def check(self, locator: str) -> None:
        """Tick a checkbox or select a radio (no-op if already checked)."""
        self._locator(locator).check()

    def uncheck(self, locator: str) -> None:
        """Untick a checkbox (no-op if already unchecked)."""
        self._locator(locator).uncheck()

    def set_checkbox(self, locator: str, checked: bool) -> None:
        """Set a checkbox to an explicit state."""
        self._locator(locator).set_checked(checked)

    def is_checked(self, locator: str) -> bool:
        """True if the checkbox or radio is selected."""
        return self._locator(locator).is_checked()

    # ============================================================
    # Native <select> dropdowns
    # ============================================================

    def select_by_value(self, locator: str, value: str) -> None:
        """Select an <option> by its value attribute."""
        self._locator(locator).select_option(value=value)

    def select_by_label(self, locator: str, label: str) -> None:
        """Select an <option> by its visible text."""
        self._locator(locator).select_option(label=label)

    def select_by_index(self, locator: str, index: int) -> None:
        """Select an <option> by its zero-based position."""
        self._locator(locator).select_option(index=index)

    def select_multiple_by_label(self, locator: str,
                                 labels: List[str]) -> None:
        """Select several options in a <select multiple>."""
        self._locator(locator).select_option(label=labels)

    def get_select_value(self, locator: str) -> str:
        """Value attribute of the chosen option."""
        return self._locator(locator).input_value()

    def get_select_label(self, locator: str) -> str:
        """Visible text of the chosen option.

        Reads el.options[el.selectedIndex].text from the DOM — a <select> whose
        chosen option is <option value="lohi">Price low-high</option> returns
        "Price low-high".
        """
        return (self._locator(locator).evaluate(
            "el => el.options[el.selectedIndex].text") or "").strip()

    def get_select_options(self, locator: str) -> List[str]:
        """Visible text of every option in a <select>."""
        return self._locator(locator).evaluate(
            "el => Array.from(el.options).map(o => o.text.trim())")

    # ============================================================
    # Custom widgets (ARIA roles) — React-Select, MUI, Ant, etc.
    # ============================================================

    def click_role(self, role: str, name: Optional[str] = None) -> None:
        """Click an element by ARIA role, optionally by accessible name.

        For div-based widgets that carry a role but no test-id.
        """
        target = (self.page.get_by_role(role, name=name) if name
                  else self.page.get_by_role(role))
        target.click()

    def get_role_text(self, role: str, name: Optional[str] = None) -> str:
        """Visible text of an element addressed by ARIA role."""
        target = (self.page.get_by_role(role, name=name) if name
                  else self.page.get_by_role(role))
        return (target.inner_text() or "").strip()

    def select_custom_option(self, trigger_locator: str,
                             option_text: str) -> None:
        """Open a custom (non-<select>) dropdown and pick an option by text."""
        self._locator(trigger_locator).click()
        self.page.get_by_role("option", name=option_text).click()

    # ============================================================
    # Hover and menus
    # ============================================================

    def hover(self, locator: str) -> None:
        """Hover over the element (reveals hover menus)."""
        self._locator(locator).hover()

    def hover_and_click(self, hover_locator: str, click_locator: str) -> None:
        """Hover to reveal a menu, then click an item inside it."""
        self._locator(hover_locator).hover()
        self._locator(click_locator).click()

    # ============================================================
    # Drag and drop
    # ============================================================

    def drag_to(self, source_locator: str, target_locator: str) -> None:
        """Drag one element onto another."""
        self._locator(source_locator).drag_to(self._locator(target_locator))

    def drag_by_offset(self, locator: str, dx: int, dy: int) -> None:
        """Drag an element by a pixel offset — for sliders and resizers."""
        source = self._locator(locator)
        box = source.bounding_box()
        if not box:
            raise ValueError(f"Element not visible, cannot drag: {locator}")
        start_x = box["x"] + box["width"] / 2
        start_y = box["y"] + box["height"] / 2
        self.page.mouse.move(start_x, start_y)
        self.page.mouse.down()
        self.page.mouse.move(start_x + dx, start_y + dy, steps=10)
        self.page.mouse.up()

    # ============================================================
    # File upload
    # ============================================================

    def upload_file(self, locator: str, file_path: Union[str, Path]) -> None:
        """Attach a single file to a file input."""
        self._locator(locator).set_input_files(str(file_path))

    def upload_files(self, locator: str,
                     file_paths: List[Union[str, Path]]) -> None:
        """Attach several files to a multi-file input."""
        self._locator(locator).set_input_files([str(p) for p in file_paths])

    def clear_uploads(self, locator: str) -> None:
        """Detach all files from a file input."""
        self._locator(locator).set_input_files([])

    # ============================================================
    # Tables and lists
    # ============================================================

    def get_row_count(self, row_locator: str) -> int:
        """Number of rows matching the row locator."""
        return self._locator(row_locator).count()

    def get_cell_text(self, row_locator: str, row_index: int,
                      cell_locator: str, cell_index: int) -> str:
        """Text of one cell, addressed by zero-based row and cell index."""
        row = self._locator(row_locator).nth(row_index)
        cell = row.locator(cell_locator).nth(cell_index)
        return (cell.inner_text() or "").strip()

    def get_column_values(self, row_locator: str, cell_locator: str,
                          cell_index: int) -> List[str]:
        """Text of one column across every row, in order."""
        values: List[str] = []
        rows = self._locator(row_locator)
        for i in range(rows.count()):
            cell = rows.nth(i).locator(cell_locator).nth(cell_index)
            values.append((cell.inner_text() or "").strip())
        return values

    def find_row_index_by_text(self, row_locator: str, text: str) -> int:
        """Index of the first row containing `text`, or -1 if none."""
        rows = self._locator(row_locator)
        for i in range(rows.count()):
            if text in (rows.nth(i).inner_text() or ""):
                return i
        return -1

    def get_nth_text(self, locator: str, index: int) -> str:
        """Text of the nth match, zero-based."""
        return (self._locator(locator).nth(index).inner_text() or "").strip()

    # ============================================================
    # Scrolling
    # ============================================================

    def scroll_into_view(self, locator: str) -> None:
        """Scroll until the element is in the viewport."""
        self._locator(locator).scroll_into_view_if_needed()

    def scroll_to_bottom(self) -> None:
        """Scroll to the bottom of the page — triggers lazy loading."""
        self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")

    def scroll_to_top(self) -> None:
        """Scroll to the top of the page."""
        self.page.evaluate("window.scrollTo(0, 0)")

    # ============================================================
    # Dialogs (alert / confirm / prompt)
    # ============================================================

    def accept_next_dialog(self, prompt_text: Optional[str] = None) -> None:
        """Auto-accept the next native dialog. Call BEFORE the trigger click."""
        def _handler(dialog: Any) -> None:
            if prompt_text is not None:
                dialog.accept(prompt_text)
            else:
                dialog.accept()

        self.page.once("dialog", _handler)

    def dismiss_next_dialog(self) -> None:
        """Auto-dismiss the next native dialog. Call BEFORE the trigger click."""
        self.page.once("dialog", lambda dialog: dialog.dismiss())

    def capture_next_dialog(self) -> Dict[str, str]:
        """Accept the next dialog and capture its message.

        Returns a dict populated once the dialog fires:
            box = page.capture_next_dialog()
            page.click(TRIGGER)
            assert box["message"] == "Are you sure?"
        """
        captured: Dict[str, str] = {}

        def _handler(dialog: Any) -> None:
            captured["message"] = dialog.message
            captured["type"] = dialog.type
            dialog.accept()

        self.page.once("dialog", _handler)
        return captured

    # ============================================================
    # New tabs and downloads
    # ============================================================

    def click_and_get_new_tab(self, locator: str) -> Page:
        """Click something that opens a new tab; return the new Page."""
        with self.page.context.expect_page() as new_page_info:
            self._locator(locator).click()
        new_page = new_page_info.value
        new_page.wait_for_load_state()
        return new_page

    def click_and_download(
        self, locator: str,
        save_dir: Union[str, Path] = "reports/downloads",
    ) -> Path:
        """Click a download trigger; save the file and return its path."""
        with self.page.expect_download() as download_info:
            self._locator(locator).click()
        download = download_info.value
        target_dir = Path(save_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        destination = target_dir / download.suggested_filename
        download.save_as(destination)
        return destination

    # ============================================================
    # Frames
    # ============================================================

    def fill_in_frame(self, frame_locator: str, locator: str,
                      value: str) -> None:
        """Fill a field inside an iframe."""
        self.page.frame_locator(frame_locator).locator(locator).fill(value)

    def click_in_frame(self, frame_locator: str, locator: str) -> None:
        """Click an element inside an iframe."""
        self.page.frame_locator(frame_locator).locator(locator).click()

    def get_text_in_frame(self, frame_locator: str, locator: str) -> str:
        """Read text from inside an iframe."""
        target = self.page.frame_locator(frame_locator).locator(locator)
        return (target.inner_text() or "").strip()