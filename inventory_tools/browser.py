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

import logging
import os

from contextlib import contextmanager
from typing import Iterator, Optional

from inventory_tools.introspect import TEST_ID_ATTRS, FRAME_DELIM

logger = logging.getLogger(__name__)

# Generic, app-agnostic login-field defaults (by input type/role, not by name).
# NOTE on `input[type='text']`: a CSS attribute selector matches the ATTRIBUTE,
# not the effective type. An input rendered as <input name="username"> with no
# `type` at all defaults to text in the browser but does NOT match
# input[type='text']. Several frameworks emit inputs that way, so relying on
# the type attribute alone makes auto-detection time out on a form that is
# perfectly ordinary.
DEFAULT_USERNAME_SELECTOR = (
    "input[type='email'], input[type='text'], "
    "input:not([type]):not([type='password'])"
)
DEFAULT_PASSWORD_SELECTOR = "input[type='password']"
DEFAULT_SUBMIT_SELECTOR = "button[type='submit'], input[type='submit']"

# Tried IN ORDER when the caller does not pass an explicit selector. A single
# comma-joined selector is not enough: `.first` then picks by DOM order rather
# than by how trustworthy the match is, so a stray search box above the form
# would win over the real username field.
_USERNAME_CANDIDATES = (
    "input[name='username']",
    "input[name*='user' i]",
    "input[name*='email' i]",
    "input[id*='user' i]",
    "input[placeholder*='user' i]",
    "input[type='email']",
    "input[type='text']",
    "input:not([type]):not([type='password'])",
)
_PASSWORD_CANDIDATES = (
    "input[type='password']",
    "input[name='password']",
    "input[name*='pass' i]",
)
_SUBMIT_CANDIDATES = (
    "button[type='submit']",
    "input[type='submit']",
    "button:has-text('Login')",
    "button:has-text('Sign in')",
)


def _first_matching(page, explicit: Optional[str], candidates: tuple,
                    what: str) -> Optional[str]:
    """First selector that matches something on the page, or None.

    An explicit selector from the caller is used as-is - if it does not match,
    that is worth failing on rather than silently guessing past it.
    """
    if explicit:
        return explicit
    for sel in candidates:
        try:
            if page.locator(sel).count() > 0:
                logger.info(f"  detected {what} field: {sel}")
                return sel
        except Exception:
            continue
    logger.warning(f"  could not find a {what} field. Tried: {', '.join(candidates)}")
    return None


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
        // A hidden form token is never something a test interacts with, and
        // its `value` is regenerated every request. Capturing one produced an
        // element literally named `uoeuu_hosiv72w_tpod_v2f_input` - a locator
        // keyed to a CSRF nonce, guaranteed stale on the next page load.
        if (el.tagName === 'INPUT' && el.type === 'hidden') continue;

        // THIRD-PARTY EMBEDS. Ad and widget networks inject links whose text
        // is rotated per impression, so every one is stale by the next page
        // load and none is part of the application under test.
        //
        // FLAGGED, NOT DROPPED. The container list below is a heuristic about
        // the web in general, not a fact about any one app, so it can be wrong
        // in both directions - it may miss a network, or catch a real element
        // that happens to sit in a similarly-named div. Silently deleting on a
        // guess would hide both mistakes. The draft surfaces these for a human
        // to delete, which is the same contract as _unstable_selectors and
        // _ambiguous_selectors already use.
        const thirdParty = !!el.closest(
          '.adsbygoogle, ins.adsbygoogle, [id^="google_ads"], [id^="aswift"], ' +
          '[id^="div-gpt-ad"], [class*="adsbygoogle"], [data-ad-client], ' +
          '[data-ad-slot], [id^="carbonads"], [class*="taboola"], [class*="outbrain"]'
        );
        const attrs = {};
        for (const a of el.attributes) attrs[a.name] = a.value;
        out.push({
          tag: el.tagName.toLowerCase(),
          attrs,
          // `value` is deliberately NOT a fallback for text. For an <input> it
          // is RUNTIME DATA - a token, a typed search term, a session id - so
          // naming or matching on it bakes one request's state into the
          // inventory. Only a real label/placeholder/name should name a field.
          //
          // textContent, NOT innerText. innerText returns the RENDERED text,
          // with CSS text-transform applied: a link styled
          // `text-transform: uppercase` renders as ALL CAPS while the DOM
          // still holds the original casing. Playwright computes the
          // accessible name from the RAW text, so a role locator built from
          // innerText resolves to ZERO. Proven 4 Aug 2026 in a browser: the
          // same node matched 0 via the rendered casing and 2 via the raw.
          text: (el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 60),
          // Kept separately: what a HUMAN sees on screen. Useful for naming
          // and for notes, never for building an accessible-name locator.
          renderedText: (el.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 60),
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
          thirdParty,
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


def _wait_for_login_form(page, timeout_ms: int = 15000) -> bool:
    """Block until a password field appears, or the timeout expires.

    A password input is the reliable signal that a login form has rendered:
    every login form has exactly one, and almost nothing else does. Waiting on
    the USERNAME field would be weaker, since apps differ wildly in how they
    mark it up - which is the whole reason _USERNAME_CANDIDATES exists.

    Returns False on timeout rather than raising: the caller already reports a
    missing form clearly, and a hard failure here would be less informative.
    """
    try:
        page.wait_for_selector("input[type='password']", state="visible",
                               timeout=timeout_ms)
        return True
    except Exception:
        logger.warning(
            f"  no password field appeared within {timeout_ms}ms at {page.url}. "
            f"The page may still be rendering, may not be a login page, or may "
            f"have redirected elsewhere."
        )
        return False


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
    # Only the URL and the credentials are required. The three SELECTORS are
    # optional by design - when they are None, _first_matching() detects them
    # against the live page. Requiring them here made auto-detection dead code:
    # do_login returned False before ever opening the page, the crawl ran
    # unauthenticated, and every URL captured the login screen instead.
    if not all([login_url, username, password]):
        logger.info("  (no login - missing url or credentials)")
        return False
    _goto_spa_tolerant(page, login_url)

    # WAIT for the form to actually render before looking for its fields.
    #
    # Two things make this necessary and they compound:
    #   1. _goto_spa_tolerant waits for `domcontentloaded`, which on a
    #      single-page app fires against an EMPTY SHELL - the form does not
    #      exist yet.
    #   2. Apps commonly redirect the root path to a real login URL, so there
    #      is a second navigation after the first one settles.
    # Detecting fields immediately therefore searches a page that has no form
    # on it, finds nothing, and the crawl proceeds unauthenticated - capturing
    # the login screen once per URL instead of the pages you asked for.
    _wait_for_login_form(page)
    url_before = page.url
    # Resolve each field against the page rather than trusting one static
    # selector. Different apps render login forms differently, and a timeout
    # here used to read as "wrong credentials" when it was really "wrong
    # selector" - a confusing failure for something the tool can detect.
    user_sel = _first_matching(page, username_selector, _USERNAME_CANDIDATES, "username")
    pass_sel = _first_matching(page, password_selector, _PASSWORD_CANDIDATES, "password")
    submit_sel = _first_matching(page, submit_selector, _SUBMIT_CANDIDATES, "submit")
    if not (user_sel and pass_sel and submit_sel):
        logger.warning(
            "  login form not recognised on this page. Pass --username-selector "
            "/ --password-selector / --submit-selector explicitly, or use "
            "--no-login if the app is public."
        )
        return False

    page.locator(user_sel).first.fill(username)
    page.locator(pass_sel).first.fill(password)
    page.locator(submit_sel).first.click()
    # 'load', not 'networkidle': an app that polls or streams never reaches
    # a quiet window. The helper below still tries networkidle, but with a
    # timeout and a fallback - that is the safe way to use it.
    page.wait_for_load_state("load")

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


def find_login_path(inventory: dict) -> str | None:
    """The login page's path, taken from the inventory itself.

    The browser tools used to default to base_url + "/" - correct only for an
    app whose root redirects to a login screen. On an app whose root is a
    public home page there is no password field there, so login failed and
    every page was then reported stale. The workaround was making the operator
    pass --login-url on every invocation, which is asking a human to supply a
    fact the inventory already records.

    Recognised by page KEY or by declared COMPONENT - `login`, `signin`,
    `sign_in`, `auth`, `logon` - so it works for whichever app is configured
    without naming any of them. Returns None when nothing matches, and the
    caller falls back to the old behaviour rather than guessing.
    """
    wanted = {"login", "signin", "sign_in", "auth", "logon", "log_in"}

    def _norm(value: str) -> str:
        return (value or "").strip().lower().replace(" ", "_").replace("-", "_")

    pages = (inventory or {}).get("pages") or {}
    # A page KEY match is the strongest signal.
    for key, entry in pages.items():
        if _norm(key) in wanted and (entry or {}).get("url"):
            return entry["url"]
    # Then a declared component.
    for entry in pages.values():
        components = (entry or {}).get("components") or []
        if any(_norm(c) in wanted for c in components) and (entry or {}).get("url"):
            return entry["url"]
    return None


def resolve_page_url(entry: dict) -> tuple[str, str | None]:
    """(path, skip_reason) for one inventory page entry.

    Some pages are a TEMPLATE, not an address - `/records/{record_id}`
    stands for one page per record. Navigating to that string literally gives a
    404 and every selector on it is then reported STALE, which is a false
    report of exactly the kind these tools exist to avoid.

    A templated entry may name a concrete page to check instead::

        "url": "/records/{record_id}",
        "url_sample": "/records/1"

    With a sample, that page is checked and the result applies to the template
    - the elements are identical for every record. Without one, the page is
    SKIPPED with a reason, never silently reported as broken.

    Returns (path, None) to proceed, or ("", reason) to skip.
    """
    url = (entry or {}).get("url") or "/"
    if "{" not in url:
        return url, None
    sample = (entry or {}).get("url_sample")
    if sample and "{" not in sample:
        return sample, None
    import re
    needed = re.findall(r"\{(\w+)\}", url)
    return "", (
        f"templated url {url!r} needs {needed} and the entry has no "
        f"`url_sample`. Add one - e.g. \"url_sample\": \"{url.split('{')[0]}1\" "
        f"- so this page can be checked against a real record."
    )


def _resolve_one(scope, selector: str):
    """Turn one inventory selector string into a Playwright Locator.

    Playwright's `locator()` selector-engine syntax understands css, `text=`
    and `role=`, but there is NO `label=`, `placeholder=`, `alt=` or `title=`
    engine — those are only reachable through the get_by_* API. The inventory emits the
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
    if selector.startswith("placeholder="):
        # getByPlaceholder. There is no `placeholder` SELECTOR ENGINE - passing
        # "placeholder=..." to locator() raises `Unknown engine "placeholder"`,
        # which surfaced as an ERROR rather than a miss and cost a verification
        # round (1 Aug 2026). The css form `[placeholder='...']` also works and
        # is what rank_selector emits; this accepts the get_by_* spelling too,
        # so an inventory written either way resolves.
        return scope.get_by_placeholder(selector[len("placeholder="):])
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