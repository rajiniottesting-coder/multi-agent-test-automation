"""Thin Playwright layer for the inventory tools (backlog 3.1).

Deliberately minimal: it drives the browser and returns plain data structures to
the pure logic in `introspect.py`. Nothing here is tied to any one application.
It captures native controls, custom widgets (ARIA role / tabindex /
contenteditable), elements inside iframes (tagged with a `frame` field and a
frame-chain selector), and open shadow DOM. Requires a Playwright browser:

    pip install playwright
    playwright install chromium
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Optional

from inventory_tools.introspect import TEST_ID_ATTRS, FRAME_DELIM

# Generic, app-agnostic login-field defaults (by input type/role, not by name).
DEFAULT_USERNAME_SELECTOR = "input[type='email'], input[type='text']"
DEFAULT_PASSWORD_SELECTOR = "input[type='password']"
DEFAULT_SUBMIT_SELECTOR = "button[type='submit'], input[type='submit']"


def _match_selector(test_attrs: tuple) -> str:
    """CSS matcher for interactive/tagged elements, incl. custom widgets.

    Includes `[id]` so id-bearing custom widgets and drag-drop targets are
    fetched; the pure-logic `_is_capturable` then keeps only those with a
    non-generated id (framework-generated ids are filtered out there).
    """
    attr_sel = ",".join(f"[{a}]" for a in test_attrs)
    return ("input,button,select,textarea,a,[role],[tabindex],[contenteditable],[id],"
            + attr_sel)


def _collect_js(test_attrs: tuple) -> str:
    """DOM-snapshot JS that also pierces OPEN shadow roots (recursive walk)."""
    return """
() => {
  const out = [];
  const SEL = '__SEL__';
  function walk(root) {
    const nodes = root.querySelectorAll('*');
    for (const el of nodes) {
      if (el.matches && el.matches(SEL)) {
        const attrs = {};
        for (const a of el.attributes) attrs[a.name] = a.value;
        out.push({
          tag: el.tagName.toLowerCase(),
          attrs,
          text: (el.innerText || el.value || '').trim().slice(0, 60),
          visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length)
        });
      }
      if (el.shadowRoot) walk(el.shadowRoot);   // pierce OPEN shadow DOM
    }
  }
  walk(document);
  return out;
}
""".replace("__SEL__", _match_selector(test_attrs).replace("'", "\\'"))


def _test_ids_js(test_attrs: tuple) -> str:
    """List live test-id values (also across open shadow DOM)."""
    attr_sel = ",".join(f"[{a}]" for a in test_attrs)
    getters = " || ".join(f"el.getAttribute('{a}')" for a in test_attrs)
    return ("""
() => {
  const out = [];
  const SEL = '__SEL__';
  function walk(root) {
    for (const el of root.querySelectorAll('*')) {
      if (el.matches && el.matches(SEL)) { const v = __GET__; if (v) out.push(v); }
      if (el.shadowRoot) walk(el.shadowRoot);
    }
  }
  walk(document);
  return out;
}
""".replace("__SEL__", attr_sel.replace("'", "\\'")).replace("__GET__", getters))


# JS (run against an iframe element) that builds a stable selector for it.
_IFRAME_SELECTOR_JS = """
el => {
  if (el.id) return "iframe#" + el.id;
  const dt = el.getAttribute('data-test') || el.getAttribute('data-testid');
  if (dt) return "iframe[data-test='" + dt + "']";
  if (el.name) return "iframe[name='" + el.name + "']";
  if (el.title) return "iframe[title='" + el.title + "']";
  const all = Array.from(el.ownerDocument.querySelectorAll('iframe'));
  const i = all.indexOf(el);
  return i >= 0 ? ("iframe >> nth=" + i) : "iframe";
}
"""


@contextmanager
def browser_page(headless: bool = True, timeout_ms: int = 15000) -> Iterator:
    """Yield a Playwright Page, cleaning up the browser afterwards."""
    from playwright.sync_api import sync_playwright  # imported lazily

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context()
        context.set_default_timeout(timeout_ms)
        page = context.new_page()
        try:
            yield page
        finally:
            context.close()
            browser.close()


def do_login(page, login_url: Optional[str], username_selector: Optional[str],
             password_selector: Optional[str], submit_selector: Optional[str],
             username: Optional[str], password: Optional[str]) -> bool:
    """Best-effort form login from explicit selectors. App-agnostic."""
    if not all([login_url, username_selector, password_selector,
                submit_selector, username, password]):
        return False
    page.goto(login_url)
    page.locator(username_selector).first.fill(username)
    page.locator(password_selector).first.fill(password)
    page.locator(submit_selector).first.click()
    page.wait_for_load_state("networkidle")
    return True


def _frame_chain_selector(page, frame) -> str:
    """Build the full outer>>>inner frame-selector chain for a sub-frame."""
    parts: list[str] = []
    f = frame
    try:
        main = page.main_frame
    except Exception:
        main = None
    while f is not None and f is not main:
        try:
            el = f.frame_element()
            parts.append(el.evaluate(_IFRAME_SELECTOR_JS))
        except Exception:
            parts.append("iframe")
        f = f.parent_frame
    return f" {FRAME_DELIM} ".join(reversed(parts)) if parts else ""


def collect_descriptors(page, url: str, test_attrs: tuple = TEST_ID_ATTRS
                        ) -> tuple[str, list[dict]]:
    """Navigate to `url`; return (page_title, element_descriptors).

    Collects the main frame plus every child frame (each element tagged with its
    frame-chain selector) and pierces open shadow DOM within each frame.
    """
    page.goto(url)
    page.wait_for_load_state("networkidle")
    js = _collect_js(test_attrs)
    descriptors = list(page.evaluate(js))
    try:
        main = page.main_frame
    except Exception:
        main = None
    for frame in page.frames:
        if frame is main:
            continue
        frame_sel = _frame_chain_selector(page, frame)
        try:
            fd = frame.evaluate(js)
        except Exception:
            continue
        for d in fd:
            if frame_sel:
                d["frame"] = frame_sel
        descriptors.extend(fd)
    return page.title(), descriptors


def _count_selector(page, selector: str) -> int:
    """Count matches for a selector, entering iframe(s) if it is frame-prefixed."""
    if FRAME_DELIM in selector:
        parts = [p.strip() for p in selector.split(FRAME_DELIM)]
        *frame_parts, elem = parts
        loc = page
        for fp in frame_parts:
            loc = loc.frame_locator(fp)
        return loc.locator(elem).count()
    return page.locator(selector).count()


def resolve_selectors(page, url: str, selectors: list[str],
                      test_attrs: tuple = TEST_ID_ATTRS
                      ) -> tuple[dict[str, int], set[str], bool]:
    """Navigate to `url`; return (counts_per_selector, live_test_ids, reachable).

    Handles frame-prefixed selectors (`iframe#x >>> [..]`), role=/text= locators,
    and open shadow DOM. `reachable` is False on navigation error / HTTP >= 400.
    """
    try:
        resp = page.goto(url)
        page.wait_for_load_state("networkidle")
    except Exception:
        return {}, set(), False
    reachable = True
    if resp is not None and resp.status >= 400:
        reachable = False
    counts: dict[str, int] = {}
    for sel in selectors:
        try:
            counts[sel] = _count_selector(page, sel)
        except Exception:
            counts[sel] = 0
    # live test-ids across main + child frames (for drift's "new element" list)
    ids_js = _test_ids_js(test_attrs)
    data_tests: set[str] = set()
    try:
        data_tests.update(page.evaluate(ids_js))
    except Exception:
        pass
    try:
        main = page.main_frame
    except Exception:
        main = None
    for frame in page.frames:
        if frame is main:
            continue
        try:
            data_tests.update(frame.evaluate(ids_js))
        except Exception:
            continue
    return counts, data_tests, reachable