"""Visually verify every selector in an inventory draft against the live page.

WHY THIS EXISTS
---------------
The inventory emits Playwright locators (`role=`, `label=`, `text=`, `>> nth=`).
That is Playwright selector-engine syntax, and Chrome DevTools cannot parse it -
pasting one into the Elements search box returns "0 of 0" even when the locator
is perfectly valid. So the mandatory draft review had no way to answer the basic
question: "which element does this actually point at?"

This opens a real browser, walks the inventory, and draws a labelled box around
each element so you can see it. Match counts are colour-coded:
    green  = 1 match   (good)
    amber  = >1 match  (ambiguous - would fail Playwright strict mode)
    red    = 0 matches (stale - selector no longer resolves)


COMMANDS
--------
Public site (no login) - add --no-login to any command below:

    # every element on every page, highlighted one by one
    python -m scripts.verify_locators --no-login

    # one page only (key from the inventory's `pages` block)
    python -m scripts.verify_locators --no-login --page login

    # only the ones that need attention (skip the healthy ones)
    python -m scripts.verify_locators --no-login --only-problems

    # ONE selector, without touching the inventory - the DevTools replacement
    python -m scripts.verify_locators --no-login \
        --selector "role=link[name='Forms']" --url /

Login-gated app - omit --no-login and it reads APP_USERS / APP_PASSWORD
from .env, logs in once, then visits every page authenticated (one browser
context for the whole run, so the session persists):

    python -m scripts.verify_locators --page dashboard

    # unusual login form (SSO, multi-step) - override the field selectors
    python -m scripts.verify_locators --page dashboard --login-url /signin \
        --username-selector "#user" --password-selector "#pass" \
        --submit-selector "input[type='submit']"

Speed / display:

    --pause 0            # no delay between highlights (fast scan)
    --pause 2            # hold each highlight 2s (slow review)
    --headless           # no window; counts only, no highlighting


EXIT CODES
----------
    0  every selector resolved to exactly one element
    1  at least one stale / ambiguous / invalid selector
    2  login failed, or --page named a page not in the inventory


RELATED TOOLS
-------------
    check_draft.py                      offline JSON sanity check, no browser
    scripts.check_inventory_staleness   same resolution check, report-only,
                                        --fail-on-drift for CI

NOTE ON LOGIN FAILURE
---------------------
If credentials are supplied but login does not succeed, this ABORTS rather than
reporting. Every page would redirect to the login screen, so every selector
would resolve to 0 and the output would read as if the whole inventory were
stale - a login problem masquerading as an inventory problem.

Requires a browser: pip install playwright && playwright install chromium

FULL FLAG REFERENCE
-------------------
Every flag, its default and its purpose:

    python -m scripts.verify_locators --help

That is the authoritative list - this docstring shows only the common
cases. --help also carries copy-pasteable examples.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from agents.app_context import AppContext
from inventory_tools import introspect
from inventory_tools.browser import (
    browser_page, do_login, _resolve_one,
    DEFAULT_USERNAME_SELECTOR, DEFAULT_PASSWORD_SELECTOR, DEFAULT_SUBMIT_SELECTOR,
)

# Injected once per page. Draws a labelled box over the element being checked -
# Playwright's own .highlight() is not visible in screenshots and vanishes on
# navigation, so we draw our own that survives long enough to be read.
_MARK_JS = """
([x, y, w, h, label, colour]) => {
  document.querySelectorAll('.__inv_mark').forEach(n => n.remove());
  const box = document.createElement('div');
  box.className = '__inv_mark';
  Object.assign(box.style, {
    position: 'absolute', left: (x + window.scrollX) + 'px',
    top: (y + window.scrollY) + 'px', width: w + 'px', height: h + 'px',
    border: '3px solid ' + colour, background: colour + '22',
    zIndex: 2147483647, pointerEvents: 'none', boxSizing: 'border-box',
  });
  const tag = document.createElement('div');
  tag.textContent = label;
  Object.assign(tag.style, {
    position: 'absolute', left: '0', top: '-22px', font: '12px monospace',
    background: colour, color: '#fff', padding: '1px 6px', whiteSpace: 'nowrap',
  });
  box.appendChild(tag);
  document.body.appendChild(box);
}
"""


def _highlight(page, locator, label: str, colour: str) -> bool:
    """Draw a labelled box over the first match. False if it is not on screen."""
    try:
        locator.first.scroll_into_view_if_needed(timeout=2000)
        box = locator.first.bounding_box()
        if not box:
            return False
        page.evaluate(_MARK_JS, [box["x"], box["y"], box["width"], box["height"],
                                 label, colour])
        return True
    except Exception:
        return False


def _verify_page(page, base_url: str, page_name: str, entry: dict,
                 pause: float, only_problems: bool) -> tuple[int, int]:
    url = base_url.rstrip("/") + (entry.get("url") or "/")
    if "<" in url:
        print(f"  [{page_name}] SKIPPED - templated url {entry.get('url')}")
        return 0, 0
    try:
        page.goto(url)
        page.wait_for_load_state("networkidle")
    except Exception as e:
        print(f"  [{page_name}] UNREACHABLE {url}: {type(e).__name__}")
        return 0, 0

    selectors = {n: s for n, s in (entry.get("elements") or {}).items()
                 if isinstance(s, str) and n != "_selector_strategies"}
    print(f"\n  [{page_name}] {url}  -  {len(selectors)} element(s)")
    ok = bad = 0
    for name, sel in selectors.items():
        try:
            count = _resolve_one(page, sel).count()
        except Exception as e:
            count = -1
            note = f"INVALID ({type(e).__name__})"
        if count == 1:
            ok += 1
            status, colour = "OK  ", "#22c55e"
        elif count == 0:
            bad += 1
            status, colour = "STALE", "#ef4444"
        elif count > 1:
            bad += 1
            status, colour = f"AMBIG({count})", "#f59e0b"
        else:
            bad += 1
            status, colour = "ERROR", "#ef4444"

        if only_problems and count == 1:
            continue

        shown = ""
        if count >= 1:
            if _highlight(page, _resolve_one(page, sel), name, colour):
                shown = "  <- highlighted"
        print(f"    {status:11} {name:28} {sel}{shown}")
        if pause and count >= 1:
            time.sleep(pause)
    return ok, bad


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="python -m scripts.verify_locators",
        description="Highlight each inventory selector on the live page so you "
                    "can see what it points at. Colour: green=1 match, "
                    "amber=ambiguous, red=stale.",
        epilog=(
            "examples:\n"
            "  public site, everything          --no-login\n"
            "  public site, one page            --no-login --page login\n"
            "  only problems                    --no-login --only-problems\n"
            "  single selector (DevTools sub)   --no-login "
            "--selector \"role=link[name='Forms']\" --url /\n"
            "  login-gated app                  --page dashboard\n"
            "  unusual login form               --page dashboard --login-url /signin "
            "--submit-selector \"input[type='submit']\"\n"
            "\nexit codes: 0=all good  1=stale/ambiguous found  2=login failed"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--page", help="Verify only this page key from the inventory.")
    ap.add_argument("--selector", help="Check ONE selector instead of the inventory.")
    ap.add_argument("--url", help="Path for --selector, e.g. /login.")
    ap.add_argument("--only-problems", action="store_true",
                    help="Show only stale/ambiguous selectors.")
    ap.add_argument("--pause", type=float, default=0.6,
                    help="Seconds to hold each highlight (default 0.6).")
    ap.add_argument("--headless", action="store_true",
                    help="Run without a visible window (no point for visual review).")
    ap.add_argument("--no-login", action="store_true",
                help="Skip login. Use for public sites.")
    ap.add_argument("--login-url",
                help="Path to the login form, e.g. /signin. Defaults to base_url.")
    ap.add_argument("--username-selector", default=DEFAULT_USERNAME_SELECTOR,
                help="Override if the username field is not auto-detected.")
    ap.add_argument("--password-selector", default=DEFAULT_PASSWORD_SELECTOR,
                help="Override if the password field is not auto-detected.")
    ap.add_argument("--submit-selector", default=DEFAULT_SUBMIT_SELECTOR,
                help="Override if the submit control is not auto-detected.")
    ap.add_argument("--username",
                    default=os.getenv("INVENTORY_USER") or os.getenv("APP_USER_STANDARD"),
                    help="Defaults to INVENTORY_USER, else APP_USER_STANDARD from .env.")
    ap.add_argument("--password",
                    default=os.getenv("INVENTORY_PASS") or os.getenv("APP_PASSWORD"),
                    help="Defaults to INVENTORY_PASS, else APP_PASSWORD from .env.")
    args = ap.parse_args()

    ctx = AppContext.load()
    base_url = ctx.base_url.rstrip("/")

    with browser_page(headless=args.headless) as page:
        if not args.no_login:
            login_url = (base_url + args.login_url) if args.login_url else base_url + "/"
            logged_in = do_login(page, login_url, args.username_selector,
                                 args.password_selector, args.submit_selector,
                                 args.username, args.password)
            if logged_in:
                print("  logged in.")
            elif not (args.username and args.password):
                print("  no credentials supplied - continuing WITHOUT login. Any page "
                      "behind auth will report every selector as STALE.\n"
                      "  Set APP_USERS / APP_PASSWORD in .env, or pass --no-login if "
                      "the app is public.")
            else:
                # ABORT. Continuing would visit the login screen for every page, so
                # every selector resolves to 0 and the report reads as if the whole
                # inventory were stale - the most misleading possible output.
                print("  ERROR: login FAILED (still on the login page).\n"
                      "    Every page would redirect to the login screen and every\n"
                      "    selector would be reported STALE - that is a login problem,\n"
                      "    not an inventory problem, so refusing to produce a\n"
                      "    misleading report.\n"
                      "    Check credentials, or pass --username-selector /\n"
                      "    --password-selector / --submit-selector if the form is not\n"
                      "    auto-detected. Re-run without --headless to watch it.")
                return 2

        # single-selector mode: no inventory needed
        if args.selector:
            url = base_url + (args.url or "/")
            page.goto(url)
            page.wait_for_load_state("networkidle")
            try:
                loc = _resolve_one(page, args.selector)
                count = loc.count()
            except Exception as e:
                print(f"  INVALID selector: {type(e).__name__}: {e}")
                return 1
            print(f"\n  {args.selector}")
            print(f"    on {url}")
            print(f"    matches: {count}")
            if count >= 1:
                print(f"    text   : {(loc.first.inner_text() or '').strip()[:70]!r}")
                _highlight(page, loc, "selector", "#22c55e")
                if not args.headless:
                    print("\n    highlighted - press Enter to close")
                    input()
            return 0 if count == 1 else 1

        inventory = json.loads(ctx.inventory_path().read_text(encoding="utf-8"))
        pages = inventory.get("pages") or {}
        if args.page:
            pages = {k: v for k, v in pages.items() if k == args.page}
            if not pages:
                print(f"  no page named {args.page!r} in the inventory")
                return 2

        total_ok = total_bad = 0
        for name, entry in pages.items():
            ok, bad = _verify_page(page, base_url, name, entry,
                                   args.pause, args.only_problems)
            total_ok += ok
            total_bad += bad

        print(f"\n  {total_ok} selector(s) resolve to exactly one element")
        print(f"  {total_bad} need attention (stale / ambiguous / invalid)")
        if not args.headless and total_bad:
            print("\n  press Enter to close the browser")
            input()
        return 1 if total_bad else 0


if __name__ == "__main__":
    raise SystemExit(main())