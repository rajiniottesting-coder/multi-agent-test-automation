"""Thin Playwright layer for the inventory tools (backlog 3.1).

Deliberately minimal: it drives the browser and returns plain data structures to
the pure logic in `introspect.py`. Nothing here needs unit tests — the testable
work lives in `introspect.py`. Requires a Playwright browser:

    pip install playwright
    playwright install chromium
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Optional

# JS run in the page to snapshot interactable / test-tagged elements.
_COLLECT_JS = """
() => {
  const out = [];
  const sel = 'input,button,select,textarea,a,[data-test],[data-testid],[data-qa]';
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
"""

# JS to list the data-test values actually present on the page.
_DATA_TESTS_JS = """
() => Array.from(document.querySelectorAll('[data-test],[data-testid],[data-qa]'))
  .map(el => el.getAttribute('data-test') || el.getAttribute('data-testid') || el.getAttribute('data-qa'))
  .filter(Boolean)
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


def login_if_configured(page, base_url: str, login_page: Optional[dict],
                        username: Optional[str], password: Optional[str]) -> None:
    """Best-effort login using the inventory's login page selectors.

    `login_page` is the inventory `pages[...]` entry for the login screen (so we
    reuse the committed selectors). No-op if credentials or selectors are absent.
    """
    if not (username and password and login_page):
        return
    els = login_page.get("elements", {})
    user_sel = els.get("username_input")
    pass_sel = els.get("password_input")
    submit_sel = els.get("login_button")
    if not (user_sel and pass_sel and submit_sel):
        return
    login_url = base_url.rstrip("/") + (login_page.get("url") or "/")
    page.goto(login_url)
    page.fill(user_sel, username)
    page.fill(pass_sel, password)
    page.click(submit_sel)
    page.wait_for_load_state("networkidle")


def collect_descriptors(page, url: str) -> tuple[str, list[dict]]:
    """Navigate to `url`; return (page_title, element_descriptors)."""
    page.goto(url)
    page.wait_for_load_state("networkidle")
    descriptors = page.evaluate(_COLLECT_JS)
    return page.title(), descriptors


def resolve_selectors(page, url: str, selectors: list[str]
                      ) -> tuple[dict[str, int], set[str], bool]:
    """Navigate to `url`; return (counts_per_selector, live_data_tests, reachable).

    `reachable` is False if navigation failed or redirected away (page gone).
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
    data_tests = set(page.evaluate(_DATA_TESTS_JS))
    return counts, data_tests, reachable