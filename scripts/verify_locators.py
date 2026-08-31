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


WHICH INVENTORY IS CHECKED  (--inventory)
----------------------------------------
By default the file named by `inventory_file` in config.yaml - i.e. the
COMMITTED inventory the agents actually use.

But the normal workflow is: generate a DRAFT -> review it -> promote it. The
draft is exactly what you need to eyeball, and it is NOT the committed file, so
point at it explicitly:

    python -m scripts.verify_locators --inventory app_inventory/app.draft.json

Without --inventory you would be verifying yesterday's committed inventory
while looking at today's draft, or hitting FileNotFoundError because the draft
has a different name. If the configured file is missing, this lists the JSON
files that ARE in app_inventory/ and shows the exact command to use.

--inventory also applies to --page: the page URL is looked up in whichever
inventory you pointed at.


COMMANDS
--------
Public site (no login) - add --no-login to any command below:

    # every element on every page, highlighted one by one
    python -m scripts.verify_locators --no-login

    # one page only (key from the inventory's `pages` block)
    python -m scripts.verify_locators --no-login --page login

    # verify a DRAFT before promoting it to the committed inventory
    python -m scripts.verify_locators --no-login --inventory app_inventory/app.draft.json

    # only the ones that need attention (skip the healthy ones)
    python -m scripts.verify_locators --no-login --only-problems

    # ONE selector, without touching the inventory - the DevTools replacement
    python -m scripts.verify_locators --no-login \
        --selector "role=link[name='Forms']" --url /

Login-gated app - omit --no-login and it reads INVENTORY_USER / INVENTORY_PASS
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

from core.app_context import AppContext
from inventory_tools import introspect
from inventory_tools.browser import (
    crawl_credentials,
    browser_page, do_login, _resolve_one, resolve_page_url, find_login_path,
    DEFAULT_USERNAME_SELECTOR, DEFAULT_PASSWORD_SELECTOR, DEFAULT_SUBMIT_SELECTOR,
)

# Injected once per page. Draws a labelled box over the element being checked -
# Playwright's own .highlight() is not visible in screenshots and vanishes on
# navigation, so we draw our own that survives long enough to be read.
_MARK_JS = """
([x, y, w, h, label, colour, clear]) => {
  // Clearing is now the CALLER's decision, made once before a batch. Doing it
  // here meant each box removed the one before it, so a 50-match family drew
  // fifty boxes and left one - the picture said "unique" while the terminal
  // said fifty.
  if (clear) document.querySelectorAll('.__inv_mark').forEach(n => n.remove());
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


def _suggest_page(wanted: str, available) -> str:
    """Closest matching page key, or "".

    Page keys are derived from URL paths, so hyphens become underscores
    (/inventory-item.html -> inventory_item). Typing the hyphenated form is the
    obvious mistake, and a bare "not found" makes the user scan a long list.
    """
    import difflib
    norm = wanted.replace("-", "_").replace(".", "_").lower()
    for key in available:
        if key.lower() == norm:
            return key
    close = difflib.get_close_matches(norm, list(available), n=1, cutoff=0.6)
    return close[0] if close else ""


# Boxing more than this locks the browser for seconds and tells you nothing
# the count did not. Enough to SEE a family - to notice it caught the header
# row too, or stopped at the fold - without waiting for it.
_MAX_HIGHLIGHTS = 25


def _highlight(page, locator, label: str, colour: str) -> bool:
    """Box EVERY match, up to a cap. False if none could be drawn.

    This drew only `locator.first`, which made a 50-match family and a
    1-match input look identical on screen: one box either way, and the count
    reported only in the terminal. Seeing all fifty is the point - it is how
    you notice that a row family also caught the header, or that a "unique"
    selector matches something further down the page you never scrolled to.

    Each box is labelled with its index so the picture matches the number.
    """
    try:
        total = locator.count()
    except Exception:                                      # noqa: BLE001
        return False
    if total == 0:
        return False

    drawn = 0
    for i in range(min(total, _MAX_HIGHLIGHTS)):
        try:
            nth = locator.nth(i)
            if i == 0:
                nth.scroll_into_view_if_needed(timeout=2000)
            box = nth.bounding_box()
            if not box:
                continue                    # off-screen or display:none
            tag = label if total == 1 else f"{label} {i + 1}/{total}"
            page.evaluate(_MARK_JS, [box["x"], box["y"], box["width"],
                                     box["height"], tag, colour, drawn == 0])
            drawn += 1
        except Exception:                                  # noqa: BLE001
            continue

    if total > _MAX_HIGHLIGHTS:
        print(f"    (boxed the first {_MAX_HIGHLIGHTS} of {total})")
    return drawn > 0


def _wait_for_render(page, selectors: dict, timeout_ms: int = 15000) -> bool:
    """Wait until the page has actually RENDERED, not merely loaded.

    `wait_for_load_state("load")` fires when the HTML and JS have arrived. On
    a single-page app that is BEFORE the framework mounts and paints anything,
    so every inventory selector is checked against an empty shell and reported
    STALE. On 31 Jul 2026 this produced 13 of 14 stale for a page whose
    selectors were demonstrably working in the E2E suite minutes earlier - the
    single one that "resolved" was the toaster, which lives in the app shell
    and therefore exists on every page.

    There is no app-agnostic readiness signal, so the page's OWN inventory is
    used as one: poll until ANY declared selector resolves. That self-
    calibrates to whatever the app is, and if nothing appears within the
    timeout the page genuinely did not render - which is a different and much
    more useful finding than a list of false stale reports.

    Returns True if something rendered.
    """
    # Require TWO distinct selectors, not one. Shell-level elements - a global
    # toaster, a nav bar - resolve on EVERY page, so a one-selector gate is
    # satisfied by the exact element that proves you are on the wrong page.
    # A second, page-specific match is what actually says "this page rendered".
    needed = 2 if len(selectors) > 1 else 1
    deadline = time.time() + timeout_ms / 1000.0
    while True:
        hits = []
        for name, sel in selectors.items():
            try:
                if _resolve_one(page, sel).count() > 0:
                    hits.append(name)
                    if len(hits) >= needed:
                        return True
            except Exception:                      # noqa: BLE001 - bad selector
                continue
        if time.time() >= deadline:
            if hits:
                print(f"    only {len(hits)} of {len(selectors)} selector(s) ever "
                      f"resolved ({', '.join(hits)}) - typically the app shell, "
                      f"not this page's content.")
            return False
        page.wait_for_timeout(250)


def _verify_page(page, base_url: str, page_name: str, entry: dict,
                 pause: float, only_problems: bool) -> tuple[int, int]:
    path, skip = resolve_page_url(entry)
    if skip:
        print(f"  [{page_name}] SKIPPED - {skip}")
        return 0, 0
    url = base_url.rstrip("/") + path
    if "<" in url:
        print(f"  [{page_name}] SKIPPED - templated url {entry.get('url')}")
        return 0, 0
    try:
        page.goto(url)
        # See note below: 'networkidle' is unreachable on apps that keep
        # background requests in flight.
        page.wait_for_load_state("load")
    except Exception as e:
        print(f"  [{page_name}] UNREACHABLE {url}: {type(e).__name__}")
        return 0, 0

    _pre = {n: s for n, s in (entry.get("elements") or {}).items()
            if isinstance(s, str) and n != "_selector_strategies"}
    if _pre and not _wait_for_render(page, _pre):
        print(f"  [{page_name}] {url}\n"
              f"    PAGE DID NOT RENDER - not one of its {len(_pre)} selectors "
              f"appeared within 15s.\n"
              f"    Nothing here is a reliable staleness report. Check that\n"
              f"    base_url is right, that login succeeded, and that this URL\n"
              f"    is not redirecting to a login or consent wall.\n"
              f"    Actual URL after navigation: {page.url}")
        return 0, 0

    selectors = {n: s for n, s in (entry.get("elements") or {}).items()
                 if isinstance(s, str) and n != "_selector_strategies"}
    print(f"\n  [{page_name}] {url}  -  {len(selectors)} element(s)")
    ok = bad = 0
    declared_family = set(entry.get("multi_match") or [])
    measured_family: list[tuple[str, int]] = []

    # The inventory already states which keys are EXPECTED to match several
    # elements, and which cannot be reached by a tool that never clicks.
    # Reporting those as faults is how a clean sweep still printed ten
    # "problems" and buried the one line that mattered.
    declared_family = set(entry.get("multi_match") or [])
    declared_conditional = set(entry.get("conditional") or [])

    for name, sel in selectors.items():
        try:
            count = _resolve_one(page, sel).count()
        except Exception as e:
            count = -1
            note = f"INVALID ({type(e).__name__})"
        expected = False
        if count == 1:
            ok += 1
            status, colour = "OK  ", "#22c55e"
        elif count == 0:
            if name in declared_conditional:
                # Declared as existing only after an interaction. This tool
                # never clicks, so zero is the correct and expected reading.
                ok += 1
                expected = True
                status, colour = "COND ", "#3b82f6"
            else:
                bad += 1
                status, colour = "STALE", "#ef4444"
        elif count > 1:
            if name in declared_family:
                # Declared multi_match. Matching several elements is the
                # declaration being SATISFIED, not a defect - the validator
                # already stops anyone clicking it.
                ok += 1
                expected = True
                status, colour = f"FAMILY({count})", "#22c55e"
            else:
                bad += 1
                status, colour = f"AMBIG({count})", "#f59e0b"
                measured_family.append((name, count))
        else:
            bad += 1
            status, colour = "ERROR", "#ef4444"

        # --only-problems means UNEXPECTED findings only. A declared family or
        # a declared conditional key is not a finding.
        if only_problems and (count == 1 or expected):
            continue

        shown = ""
        if count >= 1:
            if _highlight(page, _resolve_one(page, sel), name, colour):
                shown = "  <- highlighted"
        print(f"    {status:11} {name:28} {sel}{shown}")
        if pause and count >= 1:
            time.sleep(pause)

    # EVERY selector stale is almost never an inventory problem - it means the
    # page never loaded (wrong base_url, unreachable, redirected to a login or
    # consent wall). Saying so beats printing N STALE lines that read as if the
    # inventory rotted overnight.
    # Turn the counts into a multi_match SUGGESTION. Deliberately printed, not
    # written: a page is measured in one state, and a dropdown that happens to
    # be closed resolves to 0 or 1. Auto-editing the inventory from that would
    # silently UNCLASSIFY a real family, which is worse than not classifying it
    # at all. The human applies it; the tool only has to notice.
    unlisted = [(n, c) for n, c in measured_family if n not in declared_family]
    if unlisted:
        print(f"\n    multi_match SUGGESTION for [{page_name}] - "
              f"{len(unlisted)} key(s) matched >1 element but are not listed:")
        for n, c in unlisted:
            print(f"      {n:28} matched {c} elements")
        merged = sorted(declared_family | {n for n, _ in unlisted})
        print('      paste into the page entry:')
        print('        "multi_match": ['
              + ", ".join(f'"{n}"' for n in merged) + '],')
        print("      and give each one a `<key>_first` sibling "
              "('<selector> >> nth=0') if a test needs a single element.")

    # A declared family that measured 1 is NOT an error: a closed dropdown or an
    # unsubmitted form legitimately renders one member or none. Say so quietly
    # rather than inviting someone to delete a correct classification.
    thin = sorted(declared_family - {n for n, _ in measured_family})
    if thin:
        print(f"\n    note: declared multi_match not multiple right now "
              f"({', '.join(thin)}) - expected when the widget is closed or the "
              f"form is unsubmitted. Do NOT remove them on this evidence alone.")

    if selectors and ok == 0 and bad == len(selectors):
        print(f"    ^ ALL {bad} selectors stale - the page almost certainly did not "
              f"load as expected.\n"
              f"      Check base_url resolves to a reachable page and that you are not\n"
              f"      being redirected to a login or cookie wall.\n"
              f"      Actual URL after navigation: {page.url}")
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
            "  verify a DRAFT                   --no-login --inventory app_inventory/app.draft.json\n"
            "  single selector (DevTools sub)   --no-login "
            "--selector \"role=link[name='Forms']\" --url /\n"
            "  login-gated app                  --page dashboard\n"
            "  unusual login form               --page dashboard --login-url /signin "
            "--submit-selector \"input[type='submit']\"\n"
            "\nexit codes: 0=all good  1=stale/ambiguous found  2=login failed"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--inventory",
                    help="Inventory JSON to verify. Defaults to the file named in "
                         "config.yaml. Point it at a DRAFT to review it BEFORE "
                         "committing - that is the normal workflow.")
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
                help="Path to the login form. Defaults to the login page recorded "
                     "in the app inventory, so this is rarely needed.")
    ap.add_argument("--username-selector", default=None,
                help="Override auto-detection of the username field.")
    ap.add_argument("--password-selector", default=None,
                help="Override auto-detection of the password field.")
    ap.add_argument("--submit-selector", default=None,
                help="Override auto-detection of the submit control.")
    ap.add_argument("--username",
                    default=crawl_credentials()[0],
                    help="Defaults to INVENTORY_USER from .env.")
    ap.add_argument("--password",
                    default=crawl_credentials()[1],
                    help="Defaults to INVENTORY_PASS, else APP_PASSWORD from .env.")
    args = ap.parse_args()

    ctx = AppContext.load()
    base_url = ctx.base_url.rstrip("/")

    with browser_page(headless=args.headless) as page:
        if not args.no_login:
            # Where to SIGN IN. Priority: an explicit --login-url, then the
            # login page recorded in the inventory, then the root as a last
            # resort. Reading it from the inventory is what makes the flag
            # unnecessary in normal use - the fact is already curated, and
            # requiring an operator to repeat it is how a wrong default
            # ("/" works only if the root redirects to a login screen) stayed
            # hidden behind a workaround.
            if args.login_url:
                login_path = args.login_url
            else:
                _inv_path = Path(args.inventory) if args.inventory else ctx.inventory_path()
                try:
                    _inv = json.loads(_inv_path.read_text(encoding="utf-8"))
                except Exception:                       # noqa: BLE001
                    _inv = {}
                login_path = find_login_path(_inv) or "/"
                # This module prints; it has no logger. Using one here raised
                # NameError on the very first run for anyone who did not pass
                # --login-url, which is now the normal case.
                print(f"  login page: {login_path} (from the inventory)")
            login_url = base_url + login_path
            logged_in = do_login(page, login_url, args.username_selector,
                                 args.password_selector, args.submit_selector,
                                 args.username, args.password)
            if logged_in:
                print("  logged in.")
            elif not (args.username and args.password):
                print("  no credentials supplied - continuing WITHOUT login. Any page "
                      "behind auth will report every selector as STALE.\n"
                      "  Set INVENTORY_USER / INVENTORY_PASS in .env, or pass --no-login if "
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

        # single-selector mode
        if args.selector:
            # --page is a convenience: look the page's URL up in the inventory
            # rather than making the caller retype it. Previously --page was
            # silently IGNORED here, so the selector was checked against the site
            # root - usually the login page - and a perfectly valid locator came
            # back "matches: 0".
            path = args.url
            if args.page and not path:
                try:
                    from pathlib import Path as _P
                    inv_p = _P(args.inventory) if args.inventory else ctx.inventory_path()
                    inv = json.loads(inv_p.read_text(encoding="utf-8"))
                    entry = (inv.get("pages") or {}).get(args.page)
                    if entry is None:
                        pages_avail = inv.get("pages") or {}
                        hint = _suggest_page(args.page, pages_avail)
                        print(f"  no page named {args.page!r}.")
                        if hint:
                            print(f"    did you mean {hint!r}?  "
                                  f"(page keys use underscores, not hyphens)")
                        print(f"    available: {', '.join(sorted(pages_avail))}")
                        return 2
                    path = entry.get("url") or "/"
                    if "<" in path:
                        print(f"  page {args.page!r} has a TEMPLATED url: {path}\n"
                              f"    It cannot be visited directly - substitute a real\n"
                              f"    value and pass it explicitly, e.g.\n"
                              f"      --url \"{path.replace('<id>', '4')}\"")
                        return 2
                    print(f"  --page {args.page} -> {path}")
                except (OSError, ValueError) as e:
                    print(f"  could not read inventory for --page: {e}")
                    return 2
            url = base_url + (path or "/")
            page.goto(url)
            # 'load', not 'networkidle': an app that polls or streams
            # never goes idle, so the wait times out on a rendered page.
            page.wait_for_load_state("load")
            # ...but 'load' is BEFORE an SPA paints, so give the one selector
            # under test a chance to appear rather than reporting it stale
            # against an empty shell.
            _wait_for_render(page, {"target": args.selector})
            try:
                loc = _resolve_one(page, args.selector)
                count = loc.count()
            except Exception as e:
                print(f"  INVALID selector: {type(e).__name__}: {e}")
                return 1
            # Colour by COUNT, exactly as --page mode does. This block used to
            # paint green whatever it found, on the reasoning that a single
            # selector check is showing you what matched rather than judging
            # it. In practice the colour is the first thing a reader takes in,
            # so a 50-match family and a 1-match input looked identical - and
            # green on a page where the same tool had just reported dozens of
            # STALE entries read as a contradiction rather than an answer.
            #
            # The count still decides whether the result is right: 50 is
            # correct for a row family and wrong for a search box. The colour
            # only says which of the three cases you are in, and it now says
            # the same thing in both modes.
            if count == 0:
                verdict, colour = "STALE - nothing matched", "#ef4444"
            elif count == 1:
                verdict, colour = "OK - exactly one", "#22c55e"
            else:
                verdict, colour = (
                    f"{count} matches - a FAMILY if you meant one, AMBIGUOUS "
                    f"if you did not. Playwright is strict by default, so a "
                    f"single-element helper on this raises at run time; read "
                    f"it with the plural helpers, or scope to one row.",
                    "#f59e0b")

            print(f"\n  {args.selector}")
            print(f"    on {url}")
            print(f"    matches: {count}   {verdict}")
            if count >= 1:
                print(f"    text   : {(loc.first.inner_text() or '').strip()[:70]!r}")
                _highlight(page, loc, "selector", colour)
                if not args.headless:
                    print("\n    highlighted - press Enter to close")
                    input()
            return 0 if count == 1 else 1

        from pathlib import Path
        inv_path = Path(args.inventory) if args.inventory else ctx.inventory_path()
        if not inv_path.is_file():
            print(f"\n  ERROR: inventory not found: {inv_path}")
            drafts = sorted(inv_path.parent.glob("*.json")) if inv_path.parent.is_dir() else []
            if drafts:
                print("  files that ARE present:")
                for d in drafts:
                    print(f"    {d}")
                print("\n  Verify a draft directly:")
                print(f"    python -m scripts.verify_locators --inventory {drafts[0]}")
            else:
                print("  Generate one first:")
                print("    python -m scripts.generate_inventory --no-login --urls / "
                      "--output app_inventory/app.draft.json")
            return 2
        inventory = json.loads(inv_path.read_text(encoding="utf-8"))
        pages = inventory.get("pages") or {}
        if args.page:
            pages = {k: v for k, v in pages.items() if k == args.page}
            if not pages:
                all_pages = inventory.get("pages") or {}
                hint = _suggest_page(args.page, all_pages)
                print(f"  no page named {args.page!r} in the inventory.")
                if hint:
                    print(f"    did you mean {hint!r}?  "
                          f"(page keys use underscores, not hyphens)")
                print(f"    available: {', '.join(sorted(all_pages))}")
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