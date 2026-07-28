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

import os

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
        // Associated <label> text. Playwright's getByLabel is the recommended
        // locator for form controls, but a label is a SEPARATE DOM element
        // (<label for="x">Email</label><input id="x">), so it can never be
        // read from the element's own attributes. Captured here instead.
        label: (() => {
          try {
            if (el.labels && el.labels.length) {
              return (el.labels[0].innerText || '').trim().slice(0, 60);
            }
            const wrapping = el.closest && el.closest('label');
            if (wrapping) return (wrapping.innerText || '').trim().slice(0, 60);
          } catch (e) {}
          return '';
        })(),
          visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length),
        // Structurally UNIQUE css path, used only as the last-resort fallback.
        // Built here because it needs the live DOM tree (parent chain +
        // sibling index), which the pure ranking logic never sees. Anchored to
        // the nearest ancestor carrying a stable id so the path stays as short
        // — and therefore as resilient — as possible. Guarantees every element
        // gets a locator that resolves to exactly ONE node, instead of an
        // ambiguous tag selector that fails Playwright's strict mode.
        cssPath: (() => {
          try {
            const parts = [];
            let node = el;
            while (node && node.nodeType === 1 && node !== document.documentElement) {
              if (node.id && !/^[0-9]/.test(node.id) && !/:r[0-9a-z]+:|^radix-|^headlessui-|[0-9]{5,}/i.test(node.id)) {
                parts.unshift('#' + CSS.escape(node.id));
                break;                       // stable anchor found - stop here
              }
              const tag = node.tagName.toLowerCase();
              const parent = node.parentElement;
              if (!parent) { parts.unshift(tag); break; }
              const sibs = Array.from(parent.children).filter(
                c => c.tagName === node.tagName);
              parts.unshift(sibs.length > 1
                ? tag + ':nth-of-type(' + (sibs.indexOf(node) + 1) + ')'
                : tag);
              node = parent;
            }
            return parts.join(' > ');
          } catch (e) { return ''; }
        })()
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


def crawl_credentials() -> tuple:
    """(username, password) for the ONE login the browser tools need.

    They do not care about roles - any valid user gets them past the login
    wall. So rather than hardcoding a role name (APP_USER_STANDARD broke the
    moment the app under test renamed its roles), this takes whatever is in
    the environment:

        username: INVENTORY_USER, else the single APP_USER_<ROLE> that is set
        password: INVENTORY_PASS, else APP_PASSWORD

    With several roles set, INVENTORY_USER decides - picking one arbitrarily
    would crawl as the wrong user and produce an inventory for the wrong
    permissions level.
    """
    user = os.getenv("INVENTORY_USER")
    if not user:
        roles = [v for k, v in os.environ.items()
                 if k.startswith("APP_USER_") and v.strip()]
        user = roles[0] if len(roles) == 1 else None
    return user, (os.getenv("INVENTORY_PASS") or os.getenv("APP_PASSWORD"))


@contextmanager
def browser_page(headless: bool = True, timeout_ms: int = 30000) -> Iterator:
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

    Returns True only if the login APPEARS to have succeeded. Previously this
    returned True unconditionally, so bad credentials or a mis-detected submit
    control failed silently and the crawl captured the login form on every
    page — a draft full of username/password fields and no error anywhere.

    Success heuristic (app-agnostic, no knowledge of the landing page): the
    URL changed away from the login page, OR the password field is gone. Both
    are true of essentially every real login and neither needs app specifics.
    A False return is advisory — the caller decides whether to warn or abort.
    """
    if not all([login_url, username_selector, password_selector,
                submit_selector, username, password]):
        return False
    _goto_spa_tolerant(page, login_url)
    url_before = page.url
    page.locator(username_selector).first.fill(username)
    page.locator(password_selector).first.fill(password)
    page.locator(submit_selector).first.click()
    page.wait_for_load_state("networkidle")

    if page.url.rstrip("/") != url_before.rstrip("/"):
        return True                      # navigated away from the login page
    try:
        # Same URL: a still-present password field means we never got in
        # (SPAs that authenticate without navigating will have removed it).
        return page.locator(password_selector).count() == 0
    except Exception:
        return True                      # can't tell — don't block the run


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


def _goto_spa_tolerant(page, url: str, settle_ms: int = 3000):
    """Navigate, tolerating single-page apps that never fire `load`.

    Playwright's default `goto` waits for the `load` event. An Angular/React app
    holding an open websocket or a long poll may never fire it, so a page that
    renders perfectly still raises "Timeout 15000ms exceeded" - and the crawler
    reports 0 pages for a site that works.

    So: wait only for `domcontentloaded` (which always fires), then give the
    framework a short window to render, preferring `networkidle` but accepting
    a plain timeout. Anything actually unreachable still raises from the goto.
    """
    resp = page.goto(url, wait_until="domcontentloaded")
    try:
        page.wait_for_load_state("networkidle", timeout=settle_ms)
    except Exception:
        page.wait_for_timeout(settle_ms)      # SPA still busy - render anyway
    return resp


def collect_descriptors(page, url: str, test_attrs: tuple = TEST_ID_ATTRS
                        ) -> tuple[str, list[dict]]:
    """Navigate to `url`; return (page_title, element_descriptors).

    Collects the main frame plus every child frame (each element tagged with its
    frame-chain selector) and pierces open shadow DOM within each frame.
    """
    _goto_spa_tolerant(page, url)
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


def _resolve_one(scope, selector: str):
    """Turn one inventory selector string into a Playwright Locator.

    Playwright's `locator()` selector-engine syntax understands css, `text=`
    and `role=`, but there is NO `label=`, `alt=` or `title=` engine — those
    are only reachable through the get_by_* API. The inventory emits the
    get_by_* forms because they are the locators Playwright recommends, so
    they are translated here. Without this the staleness checker would report
    every label/alt/title selector as stale even though it resolves perfectly
    at runtime.
    """
    # ' >> nth=N' disambiguates a selector that matched several elements. For
    # css/text/role it is native locator() syntax, but a get_by_* selector must
    # have it split off and applied as .nth(N) - otherwise the index would be
    # passed into get_by_label("Email >> nth=0") as part of the text.
    if " >> nth=" in selector:
        base, _, idx = selector.rpartition(" >> nth=")
        try:
            return _resolve_one(scope, base).nth(int(idx))
        except ValueError:
            pass
    if selector.startswith("label="):
        return scope.get_by_label(selector[len("label="):])
    if selector.startswith("alt="):
        return scope.get_by_alt_text(selector[len("alt="):])
    if selector.startswith("title="):
        return scope.get_by_title(selector[len("title="):])
    # css, text= and role= are native to the selector engine.
    return scope.locator(selector)


def _count_selector(page, selector: str) -> int:
    """Count matches for a selector, entering iframe(s) if it is frame-prefixed."""
    if FRAME_DELIM in selector:
        parts = [p.strip() for p in selector.split(FRAME_DELIM)]
        *frame_parts, elem = parts
        loc = page
        for fp in frame_parts:
            loc = loc.frame_locator(fp)
        return _resolve_one(loc, elem).count()
    return _resolve_one(page, selector).count()


def resolve_selectors(page, url: str, selectors: list[str],
                      test_attrs: tuple = TEST_ID_ATTRS
                      ) -> tuple[dict[str, int], set[str], bool]:
    """Navigate to `url`; return (counts_per_selector, live_test_ids, reachable).

    Handles frame-prefixed selectors (`iframe#x >>> [..]`), role=/text= locators,
    and open shadow DOM. `reachable` is False on navigation error / HTTP >= 400.
    """
    try:
        resp = _goto_spa_tolerant(page, url)
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