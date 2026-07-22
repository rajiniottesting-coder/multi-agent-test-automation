"""Thin Playwright layer for the inventory tools (backlog 3.1).

Deliberately minimal: it drives the browser and returns plain data structures to
the pure logic in `introspect.py`. Nothing here is tied to any one application —
the test-id attributes to look for are passed in (see introspect.TEST_ID_ATTRS)
and login takes explicit selectors, so this works against any web app. Requires
a Playwright browser:

    pip install playwright
    playwright install chromium
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Optional

from inventory_tools.introspect import TEST_ID_ATTRS

# Generic, app-agnostic login-field defaults (by input type/role, not by name).
# They match a standard username+password form on any app; override per app with
# explicit selectors when the form is unusual (SSO, multi-step, custom widgets).
DEFAULT_USERNAME_SELECTOR = "input[type='email'], input[type='text']"
DEFAULT_PASSWORD_SELECTOR = "input[type='password']"
DEFAULT_SUBMIT_SELECTOR = "button[type='submit'], input[type='submit']"


def _collect_js(test_attrs: tuple) -> str:
    """Build the DOM-snapshot JS for the given test-id attributes."""
    attr_sel = ",".join(f"[{a}]" for a in test_attrs)
    return """
() => {
  const out = [];
  const sel = 'input,button,select,textarea,a,__ATTRS__';
  document.querySelectorAll(sel).forEach(el => {
    const attrs = {};
    for (const a of el.attributes) attrs[a.name] = a.value;
    out.push({
      tag: el.tagName.toLowerCase(),
      attrs,
      text: (el.innerText || el.value || '').trim().slice(0, 60),
      visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length)
    });
  });
  return out;
}
""".replace("__ATTRS__", attr_sel)


def _test_ids_js(test_attrs: tuple) -> str:
    """Build the JS that lists live test-id values for the given attributes."""
    attr_sel = ",".join(f"[{a}]" for a in test_attrs)
    getters = " || ".join(f"el.getAttribute('{a}')" for a in test_attrs)
    return ("() => Array.from(document.querySelectorAll('%s'))\n"
            "  .map(el => %s)\n"
            "  .filter(Boolean)" % (attr_sel, getters))


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
    """Best-effort form login from explicit selectors. App-agnostic.

    Returns True if a login was attempted, False if it was skipped because any
    required piece (url, selectors, credentials) was missing. The caller decides
    where those selectors come from (an inventory page, CLI flags, etc.) — this
    layer makes no assumption about element names or which page is the login page.
    """
    if not all([login_url, username_selector, password_selector,
                submit_selector, username, password]):
        return False
    page.goto(login_url)
    # .first tolerates grouped selectors (e.g. "input[type='email'], input[type='text']").
    page.locator(username_selector).first.fill(username)
    page.locator(password_selector).first.fill(password)
    page.locator(submit_selector).first.click()
    page.wait_for_load_state("networkidle")
    return True


def collect_descriptors(page, url: str, test_attrs: tuple = TEST_ID_ATTRS
                        ) -> tuple[str, list[dict]]:
    """Navigate to `url`; return (page_title, element_descriptors)."""
    page.goto(url)
    page.wait_for_load_state("networkidle")
    descriptors = page.evaluate(_collect_js(test_attrs))
    return page.title(), descriptors


def resolve_selectors(page, url: str, selectors: list[str],
                      test_attrs: tuple = TEST_ID_ATTRS
                      ) -> tuple[dict[str, int], set[str], bool]:
    """Navigate to `url`; return (counts_per_selector, live_test_ids, reachable).

    `reachable` is False if navigation failed or the page returned an error.
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
            counts[sel] = page.locator(sel).count()
        except Exception:
            counts[sel] = 0
    data_tests = set(page.evaluate(_test_ids_js(test_attrs)))
    return counts, data_tests, reachable