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
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlparse

from playwright.sync_api import Locator, Page, expect

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------
# Which helpers may be handed a multi_match key
#
# A key the inventory declares multi_match matches several elements, and
# Playwright is strict: clicking, filling or asserting on such a locator raises
# "strict mode violation: locator(...) resolved to N elements". So the selector
# validator rejects a family key unless the helper receiving it is one of these.
#
# THESE LISTS LIVE HERE, BESIDE THE HELPERS, ON PURPOSE.
#
# They used to live in the validator, as its own copy of what BasePage offers.
# Keeping two lists in step by hand failed twice, the same way both times: a
# family-aware helper was added here and recommended in the generation prompt,
# and the validator - never told - rejected the prompt's own advice. Agent 2
# then burned its repair attempts moving one call from line to line, because no
# rewrite could satisfy both voices.
#
# Adding a helper and sanctioning it are now one edit in one file. The validator
# reads these names out of this module, so the two cannot drift.

# Helpers that read or count the WHOLE match set. Safe by construction: none of
# them acts on a single element.
FAMILY_READERS = frozenset({
    "exists",
    "find_row_index_by_text",
    "get_all_texts",
    "get_cell_text",
    "get_column_values",
    "get_count",
    "get_nth_text",
    "get_row_count",
    "wait_for_count",
})

# Helpers BUILT to take a family and resolve it to one member internally -
# by text, by position, or by the row that contains something. Passing a family
# key to these is not a mistake, it is the documented signature.
FAMILY_CONSUMERS = frozenset({
    "click_in_row",
    "click_nth",
    "get_nth_attribute",
    "row_containing",
    "select_autocomplete_suggestion",
    "wait_for_row",
})

FAMILY_SAFE_HELPERS = FAMILY_READERS | FAMILY_CONSUMERS


class BasePage:
    """Every page object inherits from this."""

    # FALLBACK ONLY. The real value comes from `browser.timeout` in
    # config.yaml — see _default_timeout_ms(). This constant applies when
    # there is no readable config (unit tests, a stripped checkout).
    #
    # It used to BE the value, hard-coded, while conftest.py separately
    # applied config.yaml's `timeout` via page.set_default_timeout(). The two
    # disagreed: config said 30000, every explicit wait_visible() used 5000,
    # and a CI log would show "timeout 5000ms" on a run configured for 30s.
    # Raising the config number changed nothing, which is the worst kind of
    # knob. One source of truth now.
    DEFAULT_TIMEOUT_MS = 5000

    # Resolved browser.timeout, read once per process. None = not yet read.
    _TIMEOUT_CACHE: Optional[int] = None

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
    def page_url(cls, **params: object) -> str:
        """URL path for this page object's inventory page.

        Some pages are a TEMPLATE rather than an address: one page exists per
        record, so the inventory stores `/records/{record_id}` and the
        caller supplies the id at run time::

            self.navigate(base_url + self.page_url(record_id=42))

        Storing a sample id in the inventory instead would be worse than
        untidy: every test would silently couple to whichever record happened
        to be crawled, and the entry would read as one page when it stands for
        thousands.

        Raises:
            KeyError, naming the placeholders the template needs, when a
            templated page is opened without them - far better than navigating
            to a literal "{record_id}" and reporting every selector missing.
        """
        if not cls.INVENTORY_PAGE:
            raise RuntimeError(f"{cls.__name__} has no INVENTORY_PAGE set.")
        pages = cls._inventory().get("pages") or {}
        url = (pages.get(cls.INVENTORY_PAGE) or {}).get("url", "/")
        if "{" not in url:
            return url
        try:
            return url.format(**params)
        except KeyError as exc:
            import re as _re
            needed = _re.findall(r"\{(\w+)\}", url)
            raise KeyError(
                f"{cls.__name__}.page_url() needs {needed} to build {url!r}; "
                f"got {sorted(params) or 'none'}. This page is a template - "
                f"one page exists per record - so pass the identifier at run "
                f"time, e.g. page_url({needed[0]}=<value>)."
            ) from exc

    # ============================================================
    # Internal
    # ============================================================

    def _locator(self, locator: str) -> Locator:
        """Resolve a selector, entering iframes when it uses the ' >>> ' chain.

        'iframe#pay >>> [data-test=card]' becomes
        page.frame_locator('iframe#pay').locator('[data-test=card]').

        Clears an ad interstitial first, if one is up. This is the single
        chokepoint every action and every wait passes through, and the check
        is one string comparison against the current URL, so an interstitial
        is dismissed BEFORE a thirty-second wait begins rather than after it
        has expired. When no interstitial fragment is present - the normal
        case, every call - nothing happens at all.
        """
        self._clear_interstitial_before_acting()
        if ">>>" not in locator:
            return self._resolve(self.page, locator)
        parts = [p.strip() for p in locator.split(">>>")]
        element = parts[-1]
        scope: Any = self.page
        for frame_selector in parts[:-1]:
            scope = scope.frame_locator(frame_selector)
        return self._resolve(scope, element)

    @staticmethod
    def _resolve(scope: Any, selector: str) -> Locator:
        """Turn an inventory selector into a Playwright locator.

        `placeholder=`, `label=`, `alt=` and `title=` are NOT selector engines.
        Passing "placeholder=Some hint text" to locator() raises
        `Unknown engine "placeholder"` - which is an ERROR rather than a miss,
        so it does not read as a stale selector and sends the reader looking at
        the wrong thing.

        The sweep in inventory_tools learned this on 1 Aug 2026 and taught only
        itself. BasePage kept calling locator() directly, so an inventory
        written in the get_by_* spelling passed verify_locators and then failed
        every test that touched it: two resolvers, one vocabulary, and the tool
        meant to catch the problem could not see it. This is the same routing,
        so what the sweep accepts is exactly what the runtime accepts.
        """
        if selector.startswith("placeholder="):
            return scope.get_by_placeholder(selector[len("placeholder="):])
        if selector.startswith("label="):
            return scope.get_by_label(selector[len("label="):])
        if selector.startswith("alt="):
            return scope.get_by_alt_text(selector[len("alt="):])
        if selector.startswith("title="):
            return scope.get_by_title(selector[len("title="):])
        # css, text= and role= are native to the selector engine.
        return scope.locator(selector)

    @classmethod
    def _default_timeout_ms(cls) -> int:
        """`browser.timeout` from config.yaml, or DEFAULT_TIMEOUT_MS.

        Never raises: a missing, unreadable or non-numeric config falls back
        to the constant. A page object must not fail to construct because
        the config file moved.
        """
        if BasePage._TIMEOUT_CACHE is None:
            value = BasePage.DEFAULT_TIMEOUT_MS
            try:
                import yaml
                from config.paths import CONFIG_YAML
                cfg = yaml.safe_load(CONFIG_YAML.read_text(encoding="utf-8")) or {}
                raw = (cfg.get("browser") or {}).get("timeout")
                if isinstance(raw, bool):
                    raise TypeError("browser.timeout must be a number")
                candidate = int(raw)
                if candidate > 0:
                    value = candidate
            except Exception as exc:                      # noqa: BLE001
                logger.debug(
                    "browser.timeout unreadable (%s); using %d ms.",
                    exc, BasePage.DEFAULT_TIMEOUT_MS,
                )
            BasePage._TIMEOUT_CACHE = value
        return BasePage._TIMEOUT_CACHE

    def _timeout(self, timeout_ms: Optional[int]) -> int:
        return timeout_ms if timeout_ms is not None else self._default_timeout_ms()

    # ============================================================
    # Navigation and page state
    # ============================================================

    def navigate(self, url: str) -> None:
        """Go to an absolute URL, and FAIL NOW if the server did not serve it.

        page.goto() succeeds as long as a response arrives - a 403, a 503, a
        bot-check interstitial or a captcha page are all "successful"
        navigations to Playwright. The test then carries on and dies 30 seconds
        later on the first locator, reporting a timeout on an element that was
        never going to exist.

        That is exactly how a whole CI run failed: nine tests, nine identical
        `Locator.fill: Timeout 30000ms exceeded` errors, four and a half
        minutes burned, and the reported cause ("covered by an overlay,
        disabled, or still animating") was wrong for all nine. The page had not
        loaded at all.

        A bad status is raised immediately, naming the code and the URL, so the
        failure says what actually happened.
        """
        response = self.page.goto(url)
        if response is not None and not response.ok:
            raise AssertionError(
                f"Navigation to {url} returned HTTP {response.status} "
                f"({response.status_text}). The page did not load, so every "
                f"selector on it will time out. From CI this usually means the "
                f"host is blocking the runner's IP range, or the site is down "
                f"- check whether the same URL loads from a browser."
            )

    def click_nth(self, locator: str, index: int) -> None:
        """Click one member of a family, addressed by position.

        Page objects must never build `">> nth=" + index` themselves: that puts
        locator SYNTAX in code the selector validator cannot see into, and it
        is the one place a raw locator fragment can re-enter a page object
        after every other route has been closed off.

        The index almost always comes from find_row_index_by_text(), so the
        element is identified by what it SAYS and only then reached by where
        it sits.
        """
        try:
            self._locator(locator).nth(index).click(
                timeout=self._default_timeout_ms())
        except Exception:
            # An index past the end of the family waits out the whole timeout
            # and then reports a plain "element not found", which sends the
            # reader looking at the selector rather than at the index. Count
            # AFTER the failure - never before, because a family the app fills
            # asynchronously can legitimately be empty at the moment of asking,
            # and a pre-check would turn a passing test into a flaky one.
            try:
                found = self._locator(locator).count()
            except Exception:                                     # noqa: BLE001
                raise
            if index >= found:
                raise AssertionError(
                    f"Asked for index {index} of `{locator}`, but it matches "
                    f"{found} element(s) — valid indices are 0 to {found - 1}. "
                    f"An index is almost always the wrong way to choose: find "
                    f"the one you want by its text with "
                    f"find_row_index_by_text() and pass THAT index, so the "
                    f"test still picks the right element when the order "
                    f"changes."
                ) from None
            raise

    # Ad networks show a full-screen interstitial that SWALLOWS the first
    # navigation after a page load. Google calls its version a Vignette: the
    # click is consumed, the address gains a `#google_vignette` fragment, and
    # the page stays where it was until the ad is dismissed or times out.
    #
    # A trace showed exactly that - a nav link clicked at +3.7s, the next
    # action starting at +4.3s and waiting the full 30 seconds for an element
    # that only exists on the destination. The screenshot taken afterwards
    # showed the destination loaded and looking perfectly healthy, because by
    # then the ad had gone. Nothing in the evidence pointed at the ad.
    _INTERSTITIAL_FRAGMENTS = ("#google_vignette", "#aswift", "#dismiss")

    def _interstitial_showing(self) -> bool:
        """True when an ad interstitial is sitting over the page."""
        try:
            return any(f in (self.page.url or "")
                       for f in self._INTERSTITIAL_FRAGMENTS)
        except Exception:                                      # noqa: BLE001
            return False

    def dismiss_interstitial(self) -> bool:
        """Close an ad interstitial if one is showing. True if one was closed.

        Pressing Escape and going back are both cheap and safe: neither does
        anything when no interstitial is present, which is why this can be
        called speculatively before giving up on an action.
        """
        if not self._interstitial_showing():
            return False
        try:
            self.page.keyboard.press("Escape")
            self.page.wait_for_timeout(300)
            if self._interstitial_showing():
                self.page.go_back(wait_until="domcontentloaded")
                self.page.wait_for_timeout(300)
            return True
        except Exception:                                      # noqa: BLE001
            return False

    _clearing_interstitial = False

    def _clear_interstitial_before_acting(self) -> None:
        """Dismiss an interstitial before an action waits behind it.

        dismiss_interstitial() was added, then called from nowhere, then
        called only from the readiness probe - and the run that followed died
        in fill(), which is not a probe. An interstitial does not care which
        helper is next; it has to be cleared where EVERY helper passes, and
        that is here.

        What this does and does not fix. It clears an ad that is COVERING the
        page, which is what makes an element unclickable or invisible. It
        cannot replay a navigation the ad already swallowed: the click was
        consumed, the browser never left, and no amount of dismissing puts it
        on the page it should be on. confirm_arrival() is the answer to that
        one, and it has to be called by the page object that knows where it
        was going.

        Re-entrancy matters: dismiss_interstitial() drives the page, and the
        flag stops a recursive call from re-entering through a helper.
        """
        if self._clearing_interstitial:
            return
        if not self._interstitial_showing():
            return
        self._clearing_interstitial = True
        try:
            if self.dismiss_interstitial():
                logger.warning(
                    "%s: an ad interstitial was covering %s - dismissed it "
                    "before acting. If the step before this one navigated, it "
                    "may have been swallowed; confirm_arrival() is what "
                    "recovers that.",
                    type(self).__name__, self._where(),
                )
        finally:
            self._clearing_interstitial = False

    @classmethod
    def _declared_url(cls):
        """The raw url this page object declares in the inventory, or None.

        Raw, not resolved: a templated page keeps its `{placeholder}` so a
        caller can tell "one page per record" from a fixed address.
        """
        try:
            if not cls.INVENTORY_PAGE:
                return None
            pages = cls._inventory().get("pages") or {}
            return (pages.get(cls.INVENTORY_PAGE) or {}).get("url") or None
        except Exception:                                     # noqa: BLE001
            return None

    def _is_here(self, path: str) -> bool:
        """True if `path` is this page object's page.

        A TEMPLATED page is matched on the fixed part before the first
        placeholder: `/records/{record_id}` is "any path under /records/".
        One page exists per record, so an exact comparison is impossible and
        the prefix is the most that can honestly be checked - but it is
        enough to tell "arrived" from "never left the previous page", which
        is the only question being asked.
        """
        declared = self._declared_url()
        if not declared:
            return True                     # nothing declared: nothing to check
        if "{" in declared:
            prefix = declared.split("{", 1)[0]
            return path.startswith(prefix) and prefix.strip("/") != ""
        return path.rstrip("/") == declared.rstrip("/")

    def confirm_arrival(self, **params: object) -> None:
        """Confirm the browser reached THIS page object's page; recover if not.

        Call at the end of any page-object method that clicks a control
        expected to navigate HERE. An ad interstitial swallows the first
        navigation after a page load: the click is consumed, the address gains
        a fragment, and the browser stays exactly where it was. The next
        action then waits its whole timeout for an element on a page nobody
        reached - a trace showed exactly that, a nav click followed by a
        thirty-second wait on a URL still sitting at the previous page.

        Dismissing the ad is not enough, because the click is gone. So the
        navigation is re-issued to the URL this page object declares in the
        inventory. The destination is read from the object this is called on,
        never guessed from where the browser happens to be.

        A TEMPLATED destination - one page per record - cannot be rebuilt
        without its identifier, so it cannot be re-issued. Pass the identifier
        (`confirm_arrival(record_id=7)`) and it can. Without one, this RAISES
        rather than returning quietly: an earlier version returned, and the
        run that followed spent thirty seconds waiting for a detail-page
        control while sitting on the listing, then reported a timeout that
        pointed at the selector. Failing here names the real problem in the
        first line of the traceback.

        Silent and free when the browser is already here, which is every
        ordinary run.
        """
        from urllib.parse import urlsplit, urlunsplit

        try:
            here = urlsplit(self.page.url)
        except Exception:                                     # noqa: BLE001
            return

        if self._is_here(here.path):
            if here.fragment:
                self._clear_interstitial_before_acting()
            return

        # Not here. Clear anything covering the page and look again.
        self._clear_interstitial_before_acting()
        try:
            here = urlsplit(self.page.url)
        except Exception:                                     # noqa: BLE001
            return
        if self._is_here(here.path):
            return

        declared = self._declared_url()
        if not declared:
            return

        try:
            expected = self.page_url(**params)
        except (KeyError, RuntimeError):
            raise AssertionError(
                f"{type(self).__name__}.confirm_arrival(): the browser is at "
                f"{self.page.url}, which is not {declared}. The click that "
                f"should have navigated here did not land - on an ad-supported "
                f"site an interstitial consumes the first navigation after a "
                f"page load. This page is a TEMPLATE, so the navigation cannot "
                f"be re-issued without its identifier: pass it "
                f"(confirm_arrival(<id>=<value>)) to make this recoverable. "
                f"Refusing to continue - every selector on this page would "
                f"time out and blame itself."
            ) from None

        target = urlunsplit((here.scheme, here.netloc, expected, "", ""))
        logger.warning(
            "%s.confirm_arrival(): expected %s, found %s. The navigation that "
            "should have landed here did not - re-issuing it directly.",
            type(self).__name__, expected, self.page.url,
        )
        self.navigate(target)

    def click_in_row(self, row_locator: str, text: str, target_locator: str) -> None:
        """Click a control INSIDE the row that contains `text`.

        The alternative - find_row_index_by_text() on one family, then
        click_nth() on another - only works when the two families run in true
        lockstep, one member each per row. That is an assumption about the
        page, and pages break it routinely: a listing that renders each card's
        controls twice (once in the card, once in a hover overlay) gives one
        family 68 members and its neighbour 34, so an index found in the first
        addresses the wrong element in the second. Nothing fails loudly; the
        wrong record is acted on.

        Scoping removes the assumption. The row is found by what it SAYS, and
        the control is found INSIDE that row, so the two families never have to
        agree on cardinality or order.

        `row_locator` must match the repeating container - a table row, a card -
        not the text element within it.
        """
        row = self._locator(row_locator).filter(has_text=text)
        count = row.count()
        if count == 0:
            raise AssertionError(
                f"No row matching `{row_locator}` contains {text!r}. Check the "
                f"text is exact and that the row locator matches the repeating "
                f"CONTAINER rather than the text element inside it."
            )
        row.first.locator(target_locator).click(
            timeout=self._default_timeout_ms())

    def row_containing(self, row_locator: str, text: str) -> Locator:
        """The first row that contains `text`, for reading rather than clicking."""
        return self._locator(row_locator).filter(has_text=text).first

    def wait_for_row(self, row_locator: str, text: str,
                     present: bool = True,
                     timeout_ms: Optional[int] = None) -> None:
        """Wait until a row containing `text` is there, or is gone.

        The waiting form of "is it in the list?". Reading the whole list and
        asserting membership is a snapshot, and the moment worth checking is
        right after the action that adds or removes the row - which is exactly
        when the list is still settling.

        A run removed a product, read the names immediately, and asserted the
        name was absent. It was still there. The failure said the row had not
        been removed; only the reading had been too early.

        Use this for the presence or absence of ONE named row. Use
        wait_for_count when the NUMBER of rows is the point.
        """
        target = self._locator(row_locator).filter(has_text=text)
        if present:
            expect(target).not_to_have_count(0, timeout=self._timeout(timeout_ms))
        else:
            expect(target).to_have_count(0, timeout=self._timeout(timeout_ms))

    def get_nth_attribute(self, locator: str, index: int, name: str) -> Optional[str]:
        """Read one attribute from one member of a family."""
        return self._locator(locator).nth(index).get_attribute(name)

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

    def wait_for_page_load(self, state: str = "load",
                           timeout_ms: Optional[int] = None) -> None:
        """Wait for a load state: 'load', 'domcontentloaded' or 'networkidle'.

        Defaults to 'load', NOT 'networkidle'. A single-page app that polls,
        streams or lazy-loads never reaches a 500ms window with no in-flight
        requests, so 'networkidle' can time out on a page that has been fully
        rendered for seconds. The failure is confusing because the Playwright
        log shows the load event already fired.

        Pass state='networkidle' explicitly only when you know the page under
        test genuinely goes quiet, and give it a timeout.
        """
        self.page.wait_for_load_state(state, timeout=self._timeout(timeout_ms))

    # ============================================================
    # Waiting and element state
    # ============================================================

    def wait_visible(self, locator: str,
                     timeout_ms: Optional[int] = None) -> None:
        """Wait until the element is visible; raises if it never appears.

        Distinguishes ABSENT from HIDDEN, because they mean opposite things and
        the remedies have nothing in common:

          absent  - the element is not in the DOM. Either the selector is wrong
                    or the page is not the one the step assumed.
          hidden  - the element IS in the DOM and the app is deliberately not
                    showing it. The selector is right and the page is right;
                    the app is not in the state the step expected.

        Playwright reports both as "expected to be visible", so a hidden
        element sent a reader off to check a selector that was never at fault.
        """
        target = self._locator(locator)
        try:
            expect(target).to_be_visible(timeout=self._timeout(timeout_ms))
        except AssertionError:
            try:
                present = target.count() > 0
            except Exception:                                  # noqa: BLE001
                raise
            if present:
                raise AssertionError(
                    f"`{locator}` is PRESENT in the DOM but HIDDEN at "
                    f"{self.page.url}. The selector is correct and so is the "
                    f"page - the application is simply not in the state this "
                    f"step expected, so look at what was supposed to put it "
                    f"there rather than at the selector. A common cause is a "
                    f"scenario that assumes a starting state it never "
                    f"established: anything the application stores against the "
                    f"signed-in user usually survives logout and survives the "
                    f"run, so a previous run's leftovers are still there."
                ) from None
            raise

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

    def is_showing(self, locator: str,
                   timeout_ms: Optional[int] = None) -> bool:
        """True once the element is visible, WAITING up to the timeout.

        The readiness probe page objects should build `is_loaded()` on. The
        pattern it replaces was `try: wait_visible(...) / except: return
        False`, which discards the Playwright error — so a failing
        `assert page.is_loaded()` reported nothing but `assert False`, naming
        neither the element that never appeared nor how long it waited.

        This logs that context at WARNING before returning False, so the CI
        log alone is enough to tell a wrong selector from a slow page.

        Use is_visible() when you want a true zero-wait probe, and this when
        you are waiting for something to arrive.

        A failed probe tries ONCE more after dismissing an ad interstitial,
        and only when the URL says one is actually up. An interstitial
        swallows the navigation that was supposed to bring the browser here,
        so the probe waits on a page the browser never left - the failure
        that took a day to read, because every piece of evidence is captured
        after the ad has gone and shows the destination looking healthy.

        This is where the retry belongs: the probe is a page object asking
        "did I arrive?", and an interstitial is the thing that answers that
        question wrongly. It cannot rescue a genuine failure, because
        dismiss_interstitial() returns False without touching the page when
        no interstitial fragment is in the URL.
        """
        showing, reason = self._probe_visible(locator, timeout_ms)
        if showing:
            return True

        if self.dismiss_interstitial():
            logger.warning(
                "%s.is_showing(%r) failed behind an ad interstitial at %s — "
                "dismissed it and retried once.",
                type(self).__name__, locator, self._where(),
            )
            showing, reason = self._probe_visible(locator, timeout_ms)
            if showing:
                return True

        logger.warning(
            "%s.is_showing(%r) is False after %d ms at %s — %s",
            type(self).__name__, locator, self._timeout(timeout_ms),
            self._where(), reason,
        )
        return False

    def _where(self) -> str:
        """The current URL, or a placeholder when the page has gone away."""
        try:
            return self.page.url
        except Exception:                                 # noqa: BLE001
            return "(url unavailable)"

    def _probe_visible(self, locator: str,
                       timeout_ms: Optional[int]) -> tuple:
        """(True, "") if the element became visible, else (False, reason)."""
        try:
            self.wait_visible(locator, timeout_ms=timeout_ms)
            return True, ""
        except Exception as exc:                          # noqa: BLE001
            text = str(exc)
            return False, (text.splitlines()[0] if text else type(exc).__name__)

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

    def wait_for_count(self, locator: str, expected: int,
                       timeout_ms: Optional[int] = None) -> None:
        """Wait until exactly `expected` elements match, then return.

        The assertion form of get_count(). Playwright re-checks until the
        timeout, so this is correct immediately after an action that adds or
        removes rows - which is the only interesting moment to count.

        Prefer this to `assert page.get_count(x) == n` anywhere the number
        can still be settling, which is almost everywhere. Reading once and
        comparing turns every asynchronous update into a race, and the race
        is lost silently: the number is simply the previous one, and the
        failure blames the count rather than the wait that was never done.

        Raises AssertionError naming both numbers if the count never settles.
        """
        expect(self._locator(locator)).to_have_count(
            expected, timeout=self._timeout(timeout_ms))

    # ============================================================
    # Text inputs
    # ============================================================

    def fill(self, locator: str, value: str) -> None:
        """Clear the field and set its value in one action."""
        self._locator(locator).fill(value)

    def type_text(self, locator: str, value: str, delay_ms: int = 50) -> None:
        """Type character by character — for fields with keystroke handlers."""
        self._locator(locator).press_sequentially(value, delay=delay_ms)

    def type_and_confirm(self, locator: str, value: str,
                         delay_ms: int = 50, attempts: int = 3) -> str:
        """Enter `value`, verifying it stuck. Escalates through strategies.

        In a single-page app an input can be REPLACED by a re-render between
        the keystrokes and the submit — the framework remounts the component
        and the new element is empty. Nothing raises: the locator still
        resolves, the click still lands, and the request goes out with no
        filter at all, so the test compares against unfiltered data and fails
        somewhere far away from the cause.

        Verified 31 Jul 2026: two tests typed the same 18-character username
        into the same search box with the same helper. One produced
        `?username=...` and one produced no filter, purely on timing.

        STRATEGY ORDER MATTERS, and not for the reason it looks like.
        Reading the value back proves the FIELD holds it. It does NOT prove
        the app's model bound to it — `fill()` sets the value and reads back
        perfectly while the model stays empty, which is the original bug this
        helper exists to catch. So the keystroke strategies, which do bind,
        are tried first, and `fill()` is a last resort rather than a peer:

            1. type character by character
            2. click to focus first, then type  (the field may not have been
               mounted or focused when the first attempt ran)
            3. fill                             (last resort - may not bind)

        Each strategy is tried up to `attempts` times and verified after every
        try; a strategy that raises is logged and the next one runs, so one
        broken approach cannot end the attempt.

        Returns the strategy name that worked, for logging.

        Raises:
            AssertionError naming what the field last held. EMPTY means the
            app re-rendered and wiped it; a DIFFERENT value means the wrong
            element was targeted. Those need opposite fixes.
        """
        def _type(loc: str, val: str) -> None:
            self.clear(loc)
            self.type_text(loc, val, delay_ms=delay_ms)

        def _click_then_type(loc: str, val: str) -> None:
            self.click(loc)
            self.clear(loc)
            self.type_text(loc, val, delay_ms=delay_ms)

        def _fill(loc: str, val: str) -> None:
            self.fill(loc, val)

        strategies = (
            ("type", _type),
            ("click_then_type", _click_then_type),
            ("fill", _fill),
        )

        last = ""
        for name, strategy in strategies:
            for attempt in range(1, attempts + 1):
                try:
                    strategy(locator, value)
                    last = self.get_input_value(locator)
                except Exception as exc:                  # noqa: BLE001
                    logger.warning(
                        "%s: strategy %r raised on attempt %d/%d (%s). "
                        "Trying the next approach.",
                        locator, name, attempt, attempts, exc,
                    )
                    break
                if last == value:
                    if name != "type" or attempt > 1:
                        logger.info(
                            "%s accepted %r via %r on attempt %d.",
                            locator, value, name, attempt,
                        )
                    return name
                logger.warning(
                    "%s did not keep %r via %r on attempt %d/%d (held %r) — "
                    "the component was probably re-rendered mid-entry.",
                    locator, value, name, attempt, attempts, last,
                )

        raise AssertionError(
            f"{locator!r} would not hold {value!r} after trying "
            f"{', '.join(n for n, _ in strategies)}; it last held {last!r}. "
            f"An EMPTY field means the app re-rendered the input and wiped it "
            f"- submitting now would send no filter at all. A DIFFERENT value "
            f"means the wrong element was targeted."
        )

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

    def select_autocomplete_suggestion(
        self,
        input_locator: str,
        option_locator: str,
        query: str,
        *,
        placeholder: str = "",
        empty_text: str = "",
        timeout_ms: Optional[int] = None,
    ) -> str:
        """Type `query`, wait for a REAL suggestion, click it, return its text.

        The whole async-autocomplete dance in one call, because splitting it
        up is how it keeps going wrong. A suggestion list is populated by a
        request, and many apps render a transient placeholder row the instant
        you type. That row is a real member of the
        option family, so every naive approach picks it:

            wait for the first option    -> satisfied by the placeholder
            click option nth=0           -> clicks the placeholder
            wait for networkidle         -> a heuristic; races the render

        and selecting the placeholder selects NOTHING, which typically leaves
        the field invalid and the form silently unsubmittable - so the test
        fails several steps later on a missing confirmation rather than here.

        This waits for the placeholder to GO, then picks the first entry that
        is actually a suggestion, and clicks it by exact text.

        Args:
            input_locator:  the text field to type into
            option_locator: the suggestion FAMILY selector (matches all rows)
            query:          what to type - long enough to match something
            placeholder:    text of the transient loading row, from the app
                            inventory. Pass "" if the app has none.
            empty_text:     the app's "nothing matched" row, e.g. "No Records
                            Found". It is a real element in the family and
                            would otherwise be clicked as though it were a
                            result, so it is reported as a failure instead.
            timeout_ms:     defaults to browser.timeout from config.

        Returns:
            The text of the suggestion that was clicked, so a caller can
            assert on it or reuse it.

        Raises:
            AssertionError: naming the query AND every row that did render,
            because "no suggestion appeared" on its own tells you nothing
            about whether the request failed, returned nothing, or is still
            showing the placeholder.
        """
        self.clear(input_locator)
        # Real keystrokes: many autocompletes listen for key events and never
        # fire their request when the value is set directly.
        self.type_text(input_locator, query)

        # The list opening at all is the first signal. The placeholder counts.
        self.wait_visible(f"{option_locator} >> nth=0", timeout_ms=timeout_ms)

        if placeholder:
            # Passes immediately if the placeholder never rendered, which is
            # the correct behaviour for an app that has none or a cached list.
            self.wait_hidden(f"{option_locator} >> text={placeholder}",
                             timeout_ms=timeout_ms)

        rendered = [t.strip() for t in self.get_all_texts(option_locator)]

        if empty_text and any(empty_text.lower() in t.lower() for t in rendered):
            raise AssertionError(
                f"The app reported {empty_text!r} for {query!r}. The query "
                f"matched no record - this is the application's empty state, "
                f"not a timing problem. Use a query that matches existing data."
            )

        def _noise(text: str) -> bool:
            return bool(
                (placeholder and placeholder.lower() in text.lower())
                or (empty_text and empty_text.lower() in text.lower())
            )

        real = [t for t in rendered if t and not _noise(t)]
        if not real:
            raise AssertionError(
                f"No real suggestion for {query!r} in {input_locator!r}. "
                f"Rows rendered: {rendered!r}. Either the query matches "
                f"nothing, or it is too short for the app to fire its request."
            )

        chosen = real[0]
        # Exact text match, scoped to the family: quoting makes Playwright
        # match the whole string rather than a substring, so a suggestion
        # that is a prefix of another cannot be picked by mistake.
        self.click(f'{option_locator} >> text="{chosen}"')
        return chosen

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